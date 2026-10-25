"""Direct updates keep old files only after verified downloads succeed."""
import tempfile,threading
from pathlib import Path
from unittest.mock import patch
from launcher.mod_updates import install_selected
from launcher.mod_plan import updates
from launcher.download import DownloadCancelled,DownloadError
from tests.test_next_features import fixture,jar,release,Catalog


def setup_update(base,old_name='old.jar',new_name=None):
    old_data=jar('a');data=jar('a','2.0');old=release('a',old_data,date='2025-01-01');new=release('a',data,'2.0')
    if new_name:new['files'][0]['filename']=new_name
    repo,folder,remote=fixture(base,[old,new],{new['files'][0]['url']:data});(folder/old_name).write_bytes(old_data)
    entries,unknown=updates(remote,folder,'1.21.1','fabric');assert not unknown and len(entries)==1
    return repo,folder,remote,entries,old_data,data


def test_direct_update_downloads_then_renames_old_and_can_retry():
    with tempfile.TemporaryDirectory() as tmp:
        repo,folder,remote,entries,old_data,data=setup_update(Path(tmp))
        assert install_selected(repo,'fixture',entries)==['a-2.0.jar']
        assert not (folder/'old.jar').exists() and (folder/'old.jar.old').read_bytes()==old_data
        assert (folder/'a-2.0.jar').read_bytes()==data
        assert not (repo.game_dir/'.onion/mod-changes').exists()
        install_selected(repo,'fixture',entries)
        assert len(list(folder.glob('*.old')))==1


def test_failed_or_corrupt_download_preserves_active_original():
    for corrupt in (False,True):
        with tempfile.TemporaryDirectory() as tmp:
            repo,folder,remote,entries,old_data,data=setup_update(Path(tmp));remote.fail=not corrupt
            if corrupt:remote.blobs[entries[0]['latest']['files'][0]['url']]=b'corrupt'
            try:install_selected(repo,'fixture',entries)
            except (OSError,ValueError):pass
            else:raise AssertionError('Failed download accepted')
            assert (folder/'old.jar').read_bytes()==old_data and not list(folder.glob('*.old'))


def test_same_name_update_and_existing_old_files_are_preserved():
    with tempfile.TemporaryDirectory() as tmp:
        repo,folder,remote,entries,old_data,data=setup_update(Path(tmp),'same.jar','same.jar')
        (folder/'same.jar.old').write_bytes(b'earlier old mod')
        install_selected(repo,'fixture',entries)
        assert (folder/'same.jar').read_bytes()==data
        assert (folder/'same.jar.old').read_bytes()==b'earlier old mod'
        assert (folder/'same.jar.1.old').read_bytes()==old_data


def test_publish_failure_puts_original_filename_back():
    with tempfile.TemporaryDirectory() as tmp:
        repo,folder,remote,entries,old_data,data=setup_update(Path(tmp));rename=Path.rename
        def fail_publish(source,target):
            if source.parent.name!= 'mods' and Path(target)==folder/'a-2.0.jar':raise OSError('fixture publish failure')
            return rename(source,target)
        with patch.object(Path,'rename',fail_publish):
            try:install_selected(repo,'fixture',entries)
            except OSError:pass
            else:raise AssertionError('Publish failure hidden')
        assert (folder/'old.jar').read_bytes()==old_data and not list(folder.glob('*.old'))


def test_changed_original_target_collision_and_path_escape_are_rejected():
    for kind in ('changed','collision','escape'):
        with tempfile.TemporaryDirectory() as tmp:
            repo,folder,remote,entries,old_data,data=setup_update(Path(tmp))
            if kind=='changed':(folder/'old.jar').write_bytes(b'user changed this mod')
            elif kind=='collision':(folder/'a-2.0.jar').write_bytes(b'unrelated mod')
            else:entries[0]['latest']['files'][0]['filename']='../escape.jar'
            try:install_selected(repo,'fixture',entries)
            except (OSError,ValueError):pass
            else:raise AssertionError('Unsafe replacement accepted')
            assert (folder/'old.jar').exists() and not list(folder.glob('*.old'))


def test_cancel_and_running_instance_do_not_rename_original():
    with tempfile.TemporaryDirectory() as tmp:
        repo,folder,remote,entries,old_data,data=setup_update(Path(tmp))
        job=type('Job',(),{'cancel':threading.Event()})();job.cancel.set()
        try:install_selected(repo,'fixture',entries,job)
        except DownloadCancelled:pass
        else:raise AssertionError('Cancelled update ran')
        with patch.object(repo,'assert_idle',side_effect=RuntimeError('running')):
            try:install_selected(repo,'fixture',entries)
            except RuntimeError:pass
            else:raise AssertionError('Running instance updated')
        assert (folder/'old.jar').read_bytes()==old_data and not list(folder.glob('*.old'))


def test_unlisted_mod_is_not_network_failure_and_does_not_block_other_updates():
    with tempfile.TemporaryDirectory() as tmp:
        repo,folder,remote,entries,old_data,data=setup_update(Path(tmp));fetch=remote.fetch_json
        (folder/'custom.jar').write_bytes(jar('custom'))
        def lookup(url):
            try:return fetch(url)
            except StopIteration:raise DownloadError('HTTP request failed',http_status=404)
        remote.fetch_json=lookup
        selected,unknown=updates(remote,folder,'1.21.1','fabric')
        assert len(selected)==1 and len(unknown)==1 and '未在 Modrinth 收录' in unknown[0]
        install_selected(repo,'fixture',selected)
        assert (folder/'custom.jar').exists() and (folder/'old.jar.old').read_bytes()==old_data


def test_empty_identification_error_still_skips_only_that_file():
    with tempfile.TemporaryDirectory() as tmp:
        repo,folder,remote,entries,old_data,data=setup_update(Path(tmp));fetch=remote.fetch_json
        (folder/'custom.jar').write_bytes(jar('custom'))
        def lookup(url):
            try:return fetch(url)
            except StopIteration:raise ValueError()
        remote.fetch_json=lookup
        selected,unknown=updates(remote,folder,'1.21.1','fabric')
        assert len(selected)==1 and len(unknown)==1 and 'ValueError' in unknown[0]
