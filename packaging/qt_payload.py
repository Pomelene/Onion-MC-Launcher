"""Lossless compression of deferred GUI payloads; never patch native binaries."""
import hashlib
import json
import lzma
from pathlib import Path


def compress_payload(analysis,root):
    cache=root/'tmp'/'qt-payload'
    cache.mkdir(parents=True,exist_ok=True)
    manifest=[];datas=[];groups={'runtime':[],'optional':[]}
    for attribute in ('binaries','datas'):
        kept=[]
        for name,source,kind in getattr(analysis,attribute):
            normalized=name.replace('\\','/')
            eligible=(normalized.startswith(('PySide6/','shiboken6/')) or Path(normalized).name.startswith('Qt6')
                      or normalized=='assets/native/onion_seedmap.dll' or normalized in ('pyside6.abi3.dll','shiboken6.abi3.dll','libssl-3.dll'))
            if not eligible:kept.append((name,source,kind));continue
            group='optional' if normalized.startswith(('PySide6/plugins/','PySide6/translations/')) else 'runtime'
            groups[group].append((normalized,Path(source)))
        setattr(analysis,attribute,kept)
    for group,entries in groups.items():
        records=[];content_hash=hashlib.sha256()
        for name,source in entries:
            data=source.read_bytes();digest=hashlib.sha256(data).hexdigest()
            records.append({'path':name,'size':len(data),'sha256':digest});content_hash.update(data)
        dictionary=(16 if group=='runtime' else 8)*1024**2
        target=cache/(content_hash.hexdigest()+'.xz6n273d'+str(dictionary)+'.solid.xz')
        if not target.exists():
            filters=[{'id':lzma.FILTER_X86},{'id':lzma.FILTER_LZMA2,'preset':6,'nice_len':273,'dict_size':dictionary}]
            temporary=target.with_suffix('.tmp')
            with lzma.open(temporary,'wb',format=lzma.FORMAT_XZ,filters=filters) as output:
                for name,source in entries:
                    with source.open('rb') as stream:
                        while block:=stream.read(1024*1024):output.write(block)
            temporary.replace(target)
        packed_name='qt-payload/'+group+'.xz'
        datas.append((packed_name,str(target),'DATA'))
        manifest.append({'source':packed_name,'files':records})
    manifest_path=cache/'manifest.json'
    manifest_path.write_text(json.dumps(manifest,separators=(',',':')),encoding='utf-8')
    analysis.datas+=datas+[('qt-payload/manifest.json',str(manifest_path),'DATA')]
