from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from launcher.memory import recommended_memory
from launcher.config import Config
from launcher.version_settings import VersionSettingsStore


def test_memory_recommendation_reserves_half_and_caps_heap():
    assert recommended_memory(4096)==(1024,2048)
    assert recommended_memory(16384)==(1024,8192)
    assert recommended_memory(65536)==(1024,8192)
    assert recommended_memory(1024)==(512,512)


def test_instance_can_override_automatic_memory_both_directions():
    with TemporaryDirectory() as folder:
        root=Path(folder);cfg=Config(root/'settings.json');store=VersionSettingsStore(root/'versions.json')
        cfg.update({'auto_memory':True,'min_memory':2048,'max_memory':4096})
        with patch('launcher.memory.physical_memory_mb',return_value=12288):
            assert store.resolve('test',cfg)['max_memory']==6144
            store.set('test',{'auto_memory':False,'max_memory':3072})
            assert store.resolve('test',cfg)['max_memory']==3072
            cfg.set('auto_memory',False);store.set('test',{'auto_memory':True})
            assert store.resolve('test',cfg)['max_memory']==6144
        reloaded=VersionSettingsStore(root/'versions.json');assert reloaded.get('test')['auto_memory'] is True


def test_instance_can_clear_global_java_arguments_and_server():
    with TemporaryDirectory() as folder:
        root=Path(folder);cfg=Config(root/'settings.json');store=VersionSettingsStore(root/'versions.json')
        cfg.update({'java_path':'custom-java','jvm_args':'-Dexample=true','server_address':'example.test'})
        store.set('local',{'java_path':'','jvm_args':'','server_address':''})
        saved=VersionSettingsStore(root/'versions.json')
        values=saved.resolve('local',cfg)
        assert values['java_path']==values['jvm_args']==values['server_address']==''
        saved.clear('local');assert saved.resolve('local',cfg)['java_path']=='custom-java'
