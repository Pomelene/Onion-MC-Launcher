# -*- coding: utf-8 -*-
import json
import hashlib
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from launcher.config import Config
from launcher.download import DownloadError
from launcher.modpack import (_safe_extract, export_mrpack, read_modpack_info)
from launcher.repository import GameRepository
from tests.harness import FakeServer


def test_import_publishes_one_standalone_instance_and_rolls_back_failure():
    from launcher.modpack import import_modpack,_base_version,_detect_loader
    body=b'fixture mod';server=FakeServer({'/mod':body}).start()
    try:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=Config(root/'settings.json');config.set('game_dir',str(root/'game'))
            repo=GameRepository(config);archive=root/'fixture.mrpack'
            names=['[玉 🔍] Jade.jar','[苹果皮] appleskin.jar','[迷你HUD] minihud.jar']
            index={'name':'Fixture','versionId':'1.0','dependencies':{'minecraft':'26.3','fabric-loader':'0.19.5'},
                   'files':[{'path':'mods/'+name,'fileSize':len(body),'hashes':{'sha1':hashlib.sha1(body).hexdigest()},'downloads':[server.url('/mod')]} for name in names]}
            with zipfile.ZipFile(archive,'w') as target:
                target.writestr('modrinth.index.json',json.dumps(index,ensure_ascii=False))
                target.writestr('overrides/options.txt','fov:1.0')
            def install(self,version,*args):
                if version=='26.3':
                    folder=self.version_dir(version);folder.mkdir(parents=True,exist_ok=True)
                    (folder/f'{version}.json').write_text(json.dumps({'id':version,'mainClass':'Vanilla','downloads':{'client':{'url':server.url('/mod')}},'arguments':{'game':['--demo']}}))
                    (folder/f'{version}.jar').write_bytes(b'fixture client')
                return self.resolver.resolve(version)
            def loader(self,game,version,kind,stage):
                ident='fabric-loader-0.19.5-26.3';folder=self.version_dir(ident);folder.mkdir(parents=True)
                (folder/f'{ident}.json').write_text(json.dumps({'id':ident,'inheritsFrom':game,'mainClass':'Fabric','libraries':[{'name':'net.fabricmc:fabric-loader:0.19.5'}],'arguments':{'jvm':[{'rules':[{'action':'allow','features':{'fixture':True}}],'value':'-Dfixture=true'}]}}))
                return ident
            with patch.object(GameRepository,'install',install),patch('launcher.install.fabric.install_loader',loader):
                vid=import_modpack(repo,archive)
                assert repo.list_installed()==[vid]
                raw=repo.resolver.load_raw(vid);assert 'inheritsFrom' not in raw and 'jar' not in raw
                assert _base_version(repo,vid)=='26.3' and _detect_loader(repo,vid)==('fabric','0.19.5')
                rv=repo.resolver.resolve(vid,{'fixture':True});assert rv.main_class=='Fabric' and '-Dfixture=true' in rv.jvm_args
                assert '--demo' in rv.game_args and repo.client_jar_path(rv).read_bytes()==b'fixture client'
                for name in names:assert (repo.mods_dir(vid)/name).read_bytes()==body
                assert (repo.version_dir(vid)/'options.txt').read_text()=='fov:1.0'
                with patch.object(GameRepository,'download_jobs',side_effect=DownloadError('fixture failure')):
                    try:import_modpack(repo,archive)
                    except DownloadError:pass
                    else:raise AssertionError('Failed import was published')
                assert repo.list_installed()==[vid]
                assert not list((repo.game_dir/'.onion/install').iterdir())
    finally:server.stop()


def test_read_mrpack_info():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "pack.mrpack"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("modrinth.index.json", json.dumps({
                "name": "Test", "versionId": "1.2",
                "dependencies": {"minecraft": "1.20.4", "fabric-loader": "0.15.0"}}))
        info = read_modpack_info(p)
        assert info.kind == "mrpack"
        assert info.game_version == "1.20.4"
        assert info.loader == "fabric" and info.loader_version == "0.15.0"


def test_read_unknown_raises():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.zip"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("a.txt", "hi")
        try:
            read_modpack_info(p)
            assert False, "应当抛 DownloadError"
        except DownloadError:
            pass


def test_safe_extract_zip_slip():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.zip"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("overrides/../evil.txt", "bad")
            zf.writestr("overrides/good.txt", "ok")
        with zipfile.ZipFile(p) as zf:
            _safe_extract(zf, "overrides", Path(d) / "out")
        assert (Path(d) / "out" / "good.txt").read_bytes() == b"ok"
        assert not (Path(d) / "evil.txt").exists()


def test_export_produces_valid_mrpack():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cfg = Config(root / "settings.json")
        cfg.set("game_dir", str(root / "game"))
        repo = GameRepository(cfg)
        vdir = repo.version_dir("1.20.4")
        vdir.mkdir(parents=True)
        (vdir / "1.20.4.json").write_text(json.dumps({"id": "1.20.4", "type": "release"}),
                                             encoding="utf-8")
        (vdir / ".isolate").write_text("1", encoding="utf-8")
        mods = vdir / "mods"
        mods.mkdir()
        (mods / "mymod.jar").write_bytes(b"fakejarcontent")
        out = root / "out.mrpack"
        export_mrpack(repo, "1.20.4", out, "TestPack")
        assert out.exists()
        info = read_modpack_info(out)
        assert info.kind == "mrpack" and info.game_version == "1.20.4"
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert "modrinth.index.json" in names
            assert any(n.startswith("overrides/mods/mymod.jar") for n in names)
