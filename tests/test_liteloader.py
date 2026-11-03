import json,tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from launcher.install.liteloader import list_versions,install_loader
from launcher.download import DownloadError

def test_liteloader_profile_inherits_game_and_preserves_legacy_arguments():
    entry={'gameVersion':'1.12.2','version':'1.12.2_00','url':'https://dl.liteloader.com/versions/example.jar','libraries':[{'name':'net.minecraft:launchwrapper:1.12'}]}
    with tempfile.TemporaryDirectory() as folder:
        class Repo:
            downloader=SimpleNamespace(fetch_json=lambda url:[entry])
            def install(self,*args):return SimpleNamespace(minecraft_args='--username ${auth_player_name}')
            def version_dir(self,ident):return Path(folder)/ident
            def assert_writable(self,path):return path
        repo=Repo();assert list_versions(repo.downloader,'1.12.2')==[entry]
        name=install_loader(repo,'1.12.2','1.12.2_00');data=json.loads((Path(folder)/name/(name+'.json')).read_text())
        assert data['inheritsFrom']=='1.12.2' and data['mainClass']=='net.minecraft.launchwrapper.Launch'
        assert data['minecraftArguments']=='--username ${auth_player_name} --tweakClass com.mumfrey.liteloader.launch.LiteLoaderTweaker'
        assert data['libraries'][-1]['downloads']['artifact']['url']==entry['url']
        entry['url']='https://evil.example/file.jar'
        try:install_loader(repo,'1.12.2','1.12.2_00')
        except DownloadError:pass
        else:raise AssertionError('Untrusted LiteLoader URL accepted')


def test_litemod_is_listed_with_metadata_and_can_be_disabled():
    from launcher.mods import scan_mods,set_mod_enabled
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'test.litemod'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('litemod.json',json.dumps({'name':'Example','version':'1.2'}))
        item=scan_mods(Path(folder))[0]
        assert item.name=='Example' and item.version=='1.2' and item.enabled
        set_mod_enabled(item,False)
        assert not scan_mods(Path(folder))[0].enabled
