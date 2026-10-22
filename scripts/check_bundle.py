"""Inspect compressed one-file contents and guard Qt deployment requirements.

Reads archive metadata/code only. Does not extract credentials or user files.
Requires the development PyInstaller dependency, never shipped in the launcher.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader


def category(name):
    path=name.replace('\\','/');filename=path.rsplit('/',1)[-1]
    if filename=='opengl32sw.dll':return 'Software OpenGL'
    if path.startswith('PIL/'):return 'Pillow codecs'
    if path.startswith('PySide6/translations/'):return 'Qt translations'
    if '/plugins/' in path:return 'Qt plugins'
    if filename.startswith('Qt6') or path.startswith(('PySide6/','shiboken6/')) or filename in ('pyside6.abi3.dll','shiboken6.abi3.dll'):return 'Qt runtime and bindings'
    if filename.startswith(('python','base_library')):return 'Python interpreter and base library'
    if filename.endswith('.pyz'):return 'Python modules'
    return 'Other runtime and assets'


def inspect(path):
    path=Path(path);archive=CArchiveReader(str(path));files=[];groups=defaultdict(lambda:{'packed':0,'raw':0,'count':0})
    for name,entry in archive.toc.items():
        _,packed,raw,_,kind=entry;group=category(name)
        normalized=name.replace('\\','/')
        files.append({'file':normalized,'packed':packed,'raw':raw,'type':kind,'category':group})
        groups[group]['packed']+=packed;groups[group]['raw']+=raw;groups[group]['count']+=1
    pyz=archive.open_embedded_archive(next(k for k,v in archive.toc.items() if v[-1]=='z'))
    return {'exe':path.name,'exe_bytes':path.stat().st_size,'unpacked_archive_bytes':sum(f['raw'] for f in files),
        'groups':dict(groups),'files':sorted(files,key=lambda x:x['packed'],reverse=True),'modules':sorted(pyz.toc)}


def validate_slim(report):
    files={entry['file'] for entry in report['files']};modules=report['modules']
    assert not any(name=='PIL' or name.startswith('PIL.') for name in modules),'Unused Pillow returned'
    assert not any(name=='unittest' or name.startswith('unittest.') for name in modules),'Test tools returned'
    assert not any(name.endswith('/opengl32sw.dll') for name in files),'Unused software OpenGL returned'
    assert not any(name.split('/')[-1]=='onionmcl.json' or name.startswith(('config/','game/','runtime/','logs/')) for name in files),'Personal data path in bundle'
    for plugin in ('platforms/qwindows.dll','platforms/qoffscreen.dll','platforms/qdirect2d.dll',
                   'imageformats/qjpeg.dll','imageformats/qwebp.dll','imageformats/qtiff.dll',
                   'imageformats/qsvg.dll','imageformats/qgif.dll','imageformats/qico.dll'):
        assert 'PySide6/plugins/'+plugin in files,'Missing preserved plugin: '+plugin
    assert 'PySide6/translations/qtbase_zh_CN.qm' in files
    assert 'PySide6/translations/qtbase_ja.qm' in files
    assert 'PySide6/translations/qtbase_de.qm' in files
    for module in ('ssl','urllib.request','launcher.auth.microsoft','launcher.qtui.app'):
        assert module in modules,'Required module missing: '+module
    assert '_ssl.pyd' in files
    assert any(Path(name).name.startswith('libssl-') for name in files)
    assert any(Path(name).name.startswith('libcrypto-') for name in files)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe',type=Path);parser.add_argument('--baseline',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--max-bytes',type=int)
    parser.add_argument('--require-slim',action='store_true');args=parser.parse_args()
    report=inspect(args.exe)
    if args.require_slim:validate_slim(report)
    if args.max_bytes:assert report['exe_bytes']<=args.max_bytes,'Bundle exceeded size budget'
    if args.baseline:
        before=inspect(args.baseline);report['baseline']={k:before[k] for k in ('exe','exe_bytes','unpacked_archive_bytes','groups')}
        report['saved_bytes']=before['exe_bytes']-report['exe_bytes']
        report['saved_percent']=round(report['saved_bytes']*100/before['exe_bytes'],2)
        old_preserved={f['file'] for f in before['files'] if f['category'] in ('Qt translations','Qt plugins')}
        new_preserved={f['file'] for f in report['files'] if f['category'] in ('Qt translations','Qt plugins')}
        assert old_preserved<=new_preserved,'A previously bundled translation/plugin was removed'
        report['translations_and_plugins_preserved']=True
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('files','modules')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
