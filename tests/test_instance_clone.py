import json
import threading
import tempfile
import zipfile
from pathlib import Path
from contextlib import contextmanager

from launcher.config import Config
from launcher.repository import GameRepository
from launcher.worlds import WorldInfo, export_world


@contextmanager
def raises(expected):
    try:yield
    except expected:return
    raise AssertionError(f'Expected {expected.__name__}')


def make_repo(tmp_path, isolated=True):
    config = Config(tmp_path / 'settings.json')
    config.set('game_dir', str(tmp_path / 'game'))
    config.set('version_isolation', isolated)
    repo = GameRepository(config)
    source = repo.version_dir('26.3')
    source.mkdir(parents=True)
    (source / '26.3.json').write_text(json.dumps({'id':'26.3','jar':'26.3','mainClass':'Main'}), encoding='utf-8')
    (source / '26.3.jar').write_bytes(b'client')
    return repo, source


def check_clone_isolated_instance_keeps_version_and_data(tmp_path):
    repo, source = make_repo(tmp_path)
    (source / 'mods').mkdir()
    (source / 'mods' / 'mod.jar').write_bytes(b'mod')
    assert repo.clone_instance('26.3', '新实例') == '新实例'
    target = repo.version_dir('新实例')
    assert (target / 'mods' / 'mod.jar').read_bytes() == b'mod'
    assert (target / '新实例.jar').read_bytes() == b'client'
    assert json.loads((target / '新实例.json').read_text(encoding='utf-8'))['jar'] == '新实例'
    assert repo.resolver.resolve('新实例').id == '新实例'
    assert (target / '.isolate').is_file() and (source / '26.3.jar').is_file()
    with raises(FileExistsError):repo.clone_instance('26.3', '新实例')


def check_clone_shared_data_isolated_and_cancel_does_not_publish(tmp_path):
    repo, source = make_repo(tmp_path, isolated=False)
    (repo.game_dir / 'saves' / 'world').mkdir(parents=True)
    (repo.game_dir / 'saves' / 'world' / 'level.dat').write_bytes(b'world')
    (repo.game_dir / 'options.txt').write_text('setting', encoding='utf-8')
    repo.clone_instance('26.3','copy')
    assert repo.run_dir('copy') == repo.version_dir('copy')
    assert (repo.version_dir('copy') / 'saves' / 'world' / 'level.dat').read_bytes() == b'world'
    cancelled = threading.Event();cancelled.set()
    with raises(RuntimeError):repo.clone_instance('26.3','cancelled',cancelled)
    assert not repo.version_dir('cancelled').exists()
    assert not list(repo.versions_dir.glob('.onion-clone-*'))


def check_export_world_and_cancel_preserves_existing_destination(tmp_path):
    source=tmp_path/'saves'/'world';source.mkdir(parents=True)
    (source/'level.dat').write_bytes(b'world')
    (source/'session.lock').write_bytes(b'lock')
    dest=tmp_path/'world.zip'
    export_world(WorldInfo(source,'世界'),dest)
    with zipfile.ZipFile(dest) as archive:
        assert archive.read('world/level.dat') == b'world'
        assert 'world/session.lock' not in archive.namelist()
    original=dest.read_bytes();cancelled=threading.Event();cancelled.set()
    with raises(RuntimeError):export_world(WorldInfo(source,'世界'),dest,cancelled)
    assert dest.read_bytes() == original
    assert not list(tmp_path.glob('.onion-world-*'))


def test_clone_isolated():
    with tempfile.TemporaryDirectory() as tmp:check_clone_isolated_instance_keeps_version_and_data(Path(tmp))


def test_clone_shared_and_cancel():
    with tempfile.TemporaryDirectory() as tmp:check_clone_shared_data_isolated_and_cancel_does_not_publish(Path(tmp))


def test_world_export():
    with tempfile.TemporaryDirectory() as tmp:check_export_world_and_cancel_preserves_existing_destination(Path(tmp))


def test_bulk_mod_toggle_checks_conflicts_and_cancellation():
    from launcher.mods import read_mod_info,set_mods_enabled,scan_mods
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp);a=folder/'a.jar';b=folder/'b.jar'
        a.write_bytes(b'a');b.write_bytes(b'b')
        assert set_mods_enabled([read_mod_info(a),read_mod_info(b)],False)==2
        a_disabled=folder/'a.jar.disabled';b_disabled=folder/'b.jar.disabled'
        assert a_disabled.exists() and b_disabled.exists()
        a.write_bytes(b'conflict')
        with raises(FileExistsError):set_mods_enabled([read_mod_info(a_disabled),read_mod_info(b_disabled)],True)
        assert b_disabled.exists() and not b.exists()
        a.unlink();cancelled=threading.Event();cancelled.set()
        with raises(RuntimeError):set_mods_enabled([read_mod_info(a_disabled)],True,cancelled)
        assert a_disabled.exists() and not a.exists()
        zipped=folder/'legacy.zip';zipped.write_bytes(b'zip')
        set_mods_enabled([read_mod_info(zipped)],False)
        assert any(item.path.name=='legacy.zip.disabled' and not item.enabled for item in scan_mods(folder))
