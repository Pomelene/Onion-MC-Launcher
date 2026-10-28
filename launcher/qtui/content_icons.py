"""Read bounded embedded artwork; never extract archives to disk."""
import json
import re
import zipfile
from collections import OrderedDict
from threading import Lock
from pathlib import Path

MAX_ICON_BYTES = 2 * 1024 * 1024
_CACHE=OrderedDict()
_CACHE_BYTES=0
_LOCK=Lock()


def read_content_icon(path):
    global _CACHE_BYTES
    path=Path(path)
    try:
        info=path.stat();identity=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    except OSError:return b''
    key=str(path.absolute())
    with _LOCK:
        cached=_CACHE.get(key)
        if cached and cached[0]==identity:
            _CACHE.move_to_end(key);return cached[1]
    data=_read_content_icon(path)
    try:
        after=path.stat()
        if identity!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):return data
    except OSError:return data
    weight=len(data)+512+4*len(key)
    with _LOCK:
        old=_CACHE.pop(key,None)
        if old:_CACHE_BYTES-=old[2]
        _CACHE[key]=(identity,data,weight);_CACHE_BYTES+=weight
        while len(_CACHE)>512 or _CACHE_BYTES>16*1024**2:
            _,old=_CACHE.popitem(last=False);_CACHE_BYTES-=old[2]
    return data


def _read_content_icon(path):
    try:
        with zipfile.ZipFile(path) as archive:
            def read(name,limit):
                info=archive.getinfo(name)
                if info.file_size>limit:return b''
                with archive.open(info) as stream:return stream.read(limit+1)
            candidates=[]
            for name in ('fabric.mod.json','quilt.mod.json'):
                try:
                    data=json.loads(read(name,256*1024).decode('utf-8-sig'),strict=False)
                    value=(data.get('quilt_loader',{}).get('metadata',{}) if name.startswith('quilt') else data).get('icon')
                    if isinstance(value,dict):value=next((value[k] for k in ('128','64','32','256') if k in value),next(iter(value.values()),None))
                    if isinstance(value,str):candidates.append(value)
                except (KeyError,ValueError,TypeError,AttributeError):pass
            for name in ('META-INF/mods.toml','META-INF/neoforge.mods.toml'):
                try:
                    match=re.search(r'(?m)^\s*logoFile\s*=\s*"([^"]+)"',read(name,256*1024).decode('utf-8','replace'))
                    if match:candidates.append(match.group(1))
                except KeyError:pass
            for name in candidates+['pack.png','icon.png','logo.png']:
                try:
                    data=read(name,MAX_ICON_BYTES)
                    if data and len(data)<=MAX_ICON_BYTES:return data
                except KeyError:pass
    except (OSError,ValueError,zipfile.BadZipFile,RuntimeError):pass
    return b''
