"""Read bounded embedded artwork; never extract archives to disk."""
import json
import re
import zipfile

MAX_ICON_BYTES = 2 * 1024 * 1024


def read_content_icon(path):
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
