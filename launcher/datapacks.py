"""Safe filesystem operations for a world's data packs."""
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .safety import child, contained, recycle


@dataclass(frozen=True)
class DataPack:
    path: Path
    description: str = ''


def _metadata(path):
    try:
        if path.is_dir():
            manifest=contained(path/'pack.mcmeta', path)
            if manifest.stat().st_size>256*1024:return ''
            data=json.loads(manifest.read_text(encoding='utf-8-sig'))
        else:
            with zipfile.ZipFile(path) as archive:
                info=archive.getinfo('pack.mcmeta')
                if info.file_size>256*1024:return ''
                data=json.loads(archive.read(info).decode('utf-8-sig'))
        pack=data.get('pack',{})
        value=pack.get('description','') if isinstance(pack,dict) else ''
        if isinstance(value,dict):value=value.get('text','')
        return ' '.join(str(value).split())[:240] if isinstance(value,str) else ''
    except (OSError,ValueError,KeyError,zipfile.BadZipFile,UnicodeError):return ''


def scan(folder):
    folder=Path(folder)
    contained(folder/'probe',folder)
    if not folder.is_dir():return []
    result=[]
    for path in folder.iterdir():
        if path.name.startswith('.') or path.is_symlink() or path.is_junction():continue
        if not (path.is_dir() or path.is_file() and path.suffix.lower()=='.zip'):continue
        contained(path,folder)
        result.append(DataPack(path,_metadata(path)))
    return sorted(result,key=lambda entry:(entry.path.name.casefold(),entry.path.name))


def import_zip(folder, source):
    folder,source=Path(folder),Path(source)
    if source.suffix.lower()!='.zip':raise ValueError('请选择 ZIP 数据包')
    with zipfile.ZipFile(source) as archive:
        try:info=archive.getinfo('pack.mcmeta')
        except KeyError:raise ValueError('数据包根目录缺少 pack.mcmeta') from None
        if info.file_size>256*1024:raise ValueError('数据包信息过大')
        try:data=json.loads(archive.read(info).decode('utf-8-sig'))
        except (ValueError,UnicodeError):raise ValueError('数据包信息无效') from None
        if not isinstance(data,dict) or not isinstance(data.get('pack'),dict):raise ValueError('数据包信息无效')
    contained(folder/'probe',folder);folder.mkdir(parents=True,exist_ok=True)
    target=child(folder,source.name)
    created=False
    try:
        with source.open('rb') as src,target.open('xb') as dst:
            created=True;shutil.copyfileobj(src,dst)
    except Exception:
        if created:target.unlink(missing_ok=True)
        raise
    return target


def remove(folder,path):
    folder=Path(folder);path=contained(Path(path),folder)
    return recycle(path,folder)
