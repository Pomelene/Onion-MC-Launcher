"""Download selected mod versions, then retain replaced files with an .old suffix."""
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from .download import DownloadJob
from .mods import mod_sha1
from .mod_plan import _cancel,assert_mods_idle
from .safety import child,component


def _primary(version):
    files=version.get('files') or []
    file=next((f for f in files if f.get('primary')),files[0] if files else None)
    if not file:raise ValueError('该版本没有可下载文件')
    name=component(file['filename'])
    digest=(file.get('hashes') or {}).get('sha1','').lower()
    if not name.lower().endswith('.jar'):raise ValueError('模组文件必须为 JAR')
    if urlsplit(file['url']).scheme!='https':raise ValueError('模组下载必须使用 HTTPS')
    if len(digest)!=40 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('缺少有效文件校验值')
    if not isinstance(file.get('size'),int) or isinstance(file['size'],bool) or not 0<file['size']<=1024**3:raise ValueError('模组文件大小无效')
    return file,name,digest


def _old_name(path):
    candidate=path.with_name(path.name+'.old');number=1
    while candidate.exists():
        candidate=path.with_name(path.name+f'.{number}.old');number+=1
    return candidate


def install_selected(repo,vid,entries,job=None):
    assert_mods_idle(repo,vid);folder=repo.run_dir(vid)/'mods';repo.assert_writable(folder);folder.mkdir(parents=True,exist_ok=True)
    prepared=[];targets=set();sources=set()
    # Validate every selection before downloading or renaming anything.
    for entry in entries:
        file,name,digest=_primary(entry['latest']);target=child(folder,name)
        if name.casefold() in targets:raise ValueError('多个模组使用同一文件名：'+name)
        targets.add(name.casefold())
        source=Path(entry['path']) if entry.get('path') else None
        if source:
            if source.absolute()!=child(folder,source.name).absolute():raise ValueError('原模组不在当前实例目录内')
            if source.name.casefold() in sources:raise ValueError('同一模组不能选择多个更新版本')
            sources.add(source.name.casefold())
            repo.assert_writable(source)
        repo.assert_writable(target)
        expected=entry.get('old_sha1') or ''
        if source and not expected:
            expected=mod_sha1(source)
            known={(f.get('hashes') or {}).get('sha1','').lower() for f in (entry.get('current') or {}).get('files',[])}
            if not expected or expected not in known:raise ValueError('原模组已变化，请重新检查更新：'+source.name)
        prepared.append((source,target,file,digest,expected))
    for source,target,_,digest,expected in prepared:
        if target.is_file() and mod_sha1(target)==digest:continue
        if target.exists() and target!=source:raise FileExistsError('目标文件已存在：'+target.name)
        if source and mod_sha1(source)!=expected:raise ValueError('原模组已变化，请重新检查更新：'+source.name)
    stage=repo.game_dir/'.onion/downloads/mod-updates'/uuid.uuid4().hex;repo.assert_writable(stage)
    completed=[]
    try:
        for index,(source,target,file,digest,expected) in enumerate(prepared):
            _cancel(job)
            # Safe retries skip files that were already installed successfully.
            if target.is_file() and mod_sha1(target)==digest:
                completed.append(target.name)
                if job:job.emit((index+1,len(prepared)))
                continue
            stage.mkdir(parents=True,exist_ok=True);incoming=child(stage,target.name)
            if job:job.emit('下载 '+target.name)
            repo.downloader.download_one(DownloadJob(file['url'],incoming,sha1=digest,size=file['size'],cancel_event=job.cancel if job else None))
            if not incoming.is_file() or incoming.stat().st_size!=file['size'] or mod_sha1(incoming)!=digest:raise ValueError('下载校验失败：'+target.name)
            _cancel(job);assert_mods_idle(repo,vid)
            if source and mod_sha1(source)!=expected:raise ValueError('下载期间原模组发生变化：'+source.name)
            if target.exists() and target!=source:raise FileExistsError('目标文件已存在：'+target.name)
            old=None
            if source:
                old=_old_name(source);repo.assert_writable(old);source.rename(old)
            try:incoming.rename(target)
            except OSError:
                if old and old.exists() and not source.exists():old.rename(source)
                raise
            completed.append(target.name)
            if job:job.emit((index+1,len(prepared)))
        return completed
    finally:
        # Only this invocation's bounded, validated download files are removed.
        if stage.exists():
            for _,target,_,_,_ in prepared:
                for name in (target.name,target.name+'.part'):
                    file=child(stage,name)
                    if file.is_file():file.unlink()
            try:stage.rmdir()
            except OSError:pass
