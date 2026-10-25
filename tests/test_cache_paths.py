"""Launcher caches stay in .onion and never cross read-only roots."""
import os,tempfile
from pathlib import Path
from unittest.mock import patch
from launcher.config import Config
from launcher.repository import GameRepository
from launcher.aggregator import InfoHub
from launcher.paths import cache_dir

def test_game_cache_paths_are_hidden_and_do_not_create_old_cache():
    with tempfile.TemporaryDirectory() as tmp:
        base=Path(tmp);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'));repo=GameRepository(config)
        for relative in ('installers/forge.jar','authlib-injector.jar','modpacks/pack.mrpack','optifine/1.21/installer.jar','staging/task'):
            path=repo.cache_path(relative);assert path==repo.game_dir/'.onion/cache'/relative
            assert path.parent.is_dir()
        assert not (repo.game_dir/'.cache').exists() and not (repo.game_dir/'.craftbridge').exists()
        try:repo.cache_path('../outside')
        except (ValueError,PermissionError):pass
        else:raise AssertionError('Cache path escaped')
        if os.name=='nt':
            import ctypes
            assert ctypes.windll.kernel32.GetFileAttributesW(str(repo.game_dir/'.onion')) & 2

def test_feed_default_cache_is_inside_launcher_onion():
    with tempfile.TemporaryDirectory() as tmp:
        with patch('launcher.paths.app_root',return_value=Path(tmp)):
            hub=InfoHub(None);assert hub.cache_dir==Path(tmp)/'.onion/cache/feeds'
            hub._save_cache(next(iter(hub.statuses)),{'fixture':True})
            assert list(hub.cache_dir.glob('*.json')) and not (Path(tmp)/'config/cache').exists()
