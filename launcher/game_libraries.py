"""Saved game roots; registration never creates, moves or deletes game files."""
from pathlib import Path
from .storage import directory_key


class GameLibraries:
    def __init__(self,config):self.config=config

    def entries(self):
        result=[];seen=set()
        for entry in self.config.get('game_libraries') or []:
            path=entry.get('path','')
            if not path:continue
            key=directory_key(path)
            if key in seen:continue
            seen.add(key);result.append(dict(entry))
        return result

    def ensure_current(self):
        root=str(self.config.game_dir().resolve());key=directory_key(root);entries=self.entries()
        if not any(directory_key(item['path'])==key for item in entries):
            entries.append({'path':root,'name':'','selected_version':self.config.get('selected_version') or ''})
        values={'game_libraries':entries}
        if not self.config.get('library_legacy_root'):values['library_legacy_root']=root
        self.config.update(values)
        return entries

    def add(self,root):
        path=Path(root).expanduser().resolve()
        if not path.is_dir():raise ValueError('游戏文件夹不存在或暂时不可用')
        entries=self.entries();key=directory_key(path)
        if not any(directory_key(item['path'])==key for item in entries):
            if len(entries)>=128:raise ValueError('已保存的游戏文件夹过多')
            entries.append({'path':str(path),'name':'','selected_version':''});self.config.set('game_libraries',entries)
        return str(path)

    def remember(self,version):
        if not version and not self.config.game_dir().is_dir():return
        entries=self.entries();key=directory_key(self.config.game_dir())
        for item in entries:
            if directory_key(item['path'])==key:item['selected_version']=version
        self.config.update({'selected_version':version,'game_libraries':entries})

    def selection(self,root):
        key=directory_key(root)
        return next((entry.get('selected_version','') for entry in self.entries() if directory_key(entry['path'])==key),'')

    def rename(self,root,name):
        entries=self.entries();key=directory_key(root)
        for entry in entries:
            if directory_key(entry['path'])==key:entry['name']=str(name).strip()[:80]
        self.config.set('game_libraries',entries)

    def remove(self,root):
        key=directory_key(root)
        if key==directory_key(self.config.game_dir()):raise ValueError('请先切换到其他游戏文件夹，再从列表移除此文件夹')
        self.config.set('game_libraries',[entry for entry in self.entries() if directory_key(entry['path'])!=key])

    @staticmethod
    def title(entry):
        path=Path(entry['path'])
        return entry.get('name') or (f'{path.parent.name or path.drive} / .minecraft' if path.name=='.minecraft' else path.name or str(path))
