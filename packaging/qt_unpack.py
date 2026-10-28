"""Restore byte-identical deferred Qt files before PyInstaller's Qt runtime hook."""
import sys
from pathlib import Path


def restore(root=None):
    root=Path(root if root is not None else sys._MEIPASS)
    manifest=root/'qt-payload'/'manifest.json'
    if not manifest.is_file():return
    from hashlib import sha256
    import json
    import lzma
    import time
    from concurrent.futures import ThreadPoolExecutor
    if manifest.stat().st_size>256*1024:raise RuntimeError('Invalid GUI payload manifest')
    groups=json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(groups,list) or len(groups)>8:raise RuntimeError('Invalid GUI payload count')
    seen=set()
    for group in groups:
        source=Path(group['source'])
        if source.is_absolute() or '..' in source.parts or ':' in str(source) or not source.parts or source.parts[0]!='qt-payload':raise RuntimeError('Invalid GUI payload source')
        if not isinstance(group['files'],list) or len(group['files'])>512:raise RuntimeError('Invalid GUI payload count')
        for entry in group['files']:
            relative=Path(entry['path']);size=entry['size']
            if (relative.is_absolute() or '..' in relative.parts or ':' in str(relative) or not relative.parts
                    or str(relative).casefold() in seen or not isinstance(size,int) or not 0<size<=128*1024**2):
                raise RuntimeError('Invalid GUI payload path or size')
            seen.add(str(relative).casefold())

    def verified(path,entry):
        if not path.is_file() or path.stat().st_size!=entry['size']:return False
        digest=sha256()
        with path.open('rb') as stream:
            while block:=stream.read(256*1024):digest.update(block)
        return digest.hexdigest()==entry['sha256']

    def unpack(group):
        source=root/group['source']
        if not source.exists() and all(verified(root/item['path'],item) for item in group['files']):return
        with lzma.open(source,'rb') as compressed:
            for entry in group['files']:
                target=root/entry['path'];target.parent.mkdir(parents=True,exist_ok=True)
                temporary=target.with_name(target.name+'.unpack');digest=sha256();remaining=entry['size']
                try:
                    with temporary.open('xb') as output:
                        while remaining:
                            block=compressed.read(min(256*1024,remaining))
                            if not block:raise RuntimeError('GUI payload ended before declared size')
                            remaining-=len(block);digest.update(block);output.write(block)
                    if digest.hexdigest()!=entry['sha256']:raise RuntimeError('GUI payload integrity check failed')
                    for attempt in range(5):
                        try:
                            temporary.replace(target);break
                        except OSError as error:
                            if getattr(error,'winerror',None) not in (5,32,33) or attempt==4:raise
                            time.sleep(.02*2**attempt)
                finally:temporary.unlink(missing_ok=True)
            if compressed.read(1):raise RuntimeError('GUI payload exceeded declared size')
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='onion-runtime') as pool:list(pool.map(unpack,groups))
    for group in groups:(root/group['source']).unlink(missing_ok=True)


if getattr(sys,'frozen',False):restore()
