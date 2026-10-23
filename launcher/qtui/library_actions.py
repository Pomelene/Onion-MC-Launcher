"""Switch repositories as a unit, including settings, metadata and async views."""
from pathlib import Path
from PySide6.QtWidgets import QLineEdit
from ..storage import directory_key


class LibraryActions:
    def bind_game_library(self):
        from ..instance import InstanceStore
        from ..version_settings import VersionSettingsStore
        from ..storage import is_portable
        portable=self.config_obj.path if is_portable(self.config_obj.path) else None
        legacy=self.config_obj.get('library_legacy_root');root=self.repo.game_dir
        self.instances=InstanceStore(portable or self.root/'config/instances.json',root,legacy)
        self.version_settings=VersionSettingsStore(portable or self.root/'config/version_settings.json',root,legacy)

    def switch_game_library(self,path):
        path=Path(path).expanduser().resolve()
        if directory_key(path)==directory_key(self.repo.game_dir):return True
        if self.mutating or self.launch_pending:
            self.status.setText('请等待当前安装或启动准备完成后切换游戏文件夹');return False
        if not path.is_dir():self.error('游戏文件夹不存在或暂时不可用：'+str(path));return False
        if not self.flush_settings():return False
        try:
            self.game_libraries.remember(self.selected_version)
            self.game_libraries.add(path)
            selected=self.game_libraries.selection(path)
            self.config_obj.update({'game_dir':str(path),'selected_version':selected})
            self.activate_game_library(selected)
            return True
        except Exception as error:self.error(error);return False

    def activate_game_library(self,selected=None):
        """Also used by the existing settings path editor after a validated save."""
        from ..repository import GameRepository
        from .widgets import clear
        self.repo=GameRepository(self.config_obj);self.game_libraries.ensure_current();self.bind_game_library()
        self.selected_version=self.game_libraries.selection(self.repo.game_dir) if selected is None else selected
        self.versions=[];self.kinds={};self.instance_context='';self.instance_editor=None
        self.logs.setParent(None);clear(self.page_map['instance'].body)
        for key in list(self.page_seq):self.page_seq[key]+=1
        self.nav_history=[]
        if self.settings_editor and isinstance(self.settings_editor.fields.get('game_dir'),QLineEdit):
            field=self.settings_editor.fields['game_dir'];previous=field.blockSignals(True)
            field.setText(str(self.repo.game_dir));field.blockSignals(previous)
        self.selector.blockSignals(True);self.selector.clear();self.selector.blockSignals(False)
        self.status.setText('');self.update_selection();self.reload_versions()

    def add_game_library(self,path):
        try:
            if self.mutating or self.launch_pending:
                self.status.setText('请等待当前任务完成后添加游戏文件夹');return False
            return self.switch_game_library(self.game_libraries.add(path))
        except Exception as error:self.error(error);return False

    def remove_game_library(self,path):
        try:self.game_libraries.remove(path);self.build_versions();self.build_sidebar('versions');return True
        except Exception as error:self.error(error);return False
