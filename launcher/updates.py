"""Declarative update discovery and verified, transactional Windows replacement."""
import base64
import hashlib
import json
import os
import platform
import re
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .download import Downloader,DownloadJob,DownloadError,DownloadCancelled
from .network import fetch_public,validate_url
from .paths import LAUNCHER_VERSION,LAUNCHER_UPDATE_ORDER

MANIFEST_URL='https://api.github.com/repos/Pomelene/OnionService4THUnion/contents/updates.json'
MAX_MANIFEST=128*1024
MAX_EXE=256*1024**2


@dataclass(frozen=True)
class Release:
    series:str
    version:str
    order:int
    platform:str
    url:str
    size:int
    sha256:str
    notes:str=''
    supports_updater:bool=False


def edition(version=LAUNCHER_VERSION):
    return 'thunion' if version.endswith('-T') else 'public'


def parse_manifest(data):
    if not isinstance(data,dict) or type(data.get('schema_version')) is not int or data['schema_version']!=1:
        raise ValueError('不支持的版本目录')
    entries=data.get('releases')
    if not isinstance(entries,list) or len(entries)>128:raise ValueError('版本目录格式无效')
    result=[];seen=set()
    for item in entries:
        if not isinstance(item,dict):raise ValueError('版本信息无效')
        series=item.get('series');version=item.get('version');order=item.get('order');target=item.get('platform')
        if series not in ('public','thunion') or not isinstance(version,str) or not re.fullmatch(r'\d+(?:\.\d+){1,3}(?:-T)?',version) or edition(version)!=series:
            raise ValueError('版本系列无效')
        if type(order) is not int or not 1<=order<=2**53 or target!='windows-x64':raise ValueError('版本排序或平台无效')
        identity=(series,target,order)
        if identity in seen:raise ValueError('版本排序重复')
        seen.add(identity)
        url=validate_url(item.get('url'),https_only=True);parsed=urllib.parse.urlsplit(url)
        # A catalog can choose a release, never a script or an arbitrary host.
        if parsed.hostname!='github.com' or parsed.port not in (None,443) or not parsed.path.startswith('/Pomelene/Onion-MC-Launcher/releases/download/v'+version+'/') or not parsed.path.lower().endswith('.exe') or parsed.query or parsed.fragment:
            raise ValueError('更新文件必须来自启动器的 GitHub Release')
        size=item.get('size');digest=item.get('sha256');notes=item.get('notes','')
        if type(size) is not int or not 1<=size<=MAX_EXE or not isinstance(digest,str) or not re.fullmatch('[0-9a-fA-F]{64}',digest):raise ValueError('更新文件校验信息无效')
        if not isinstance(notes,str) or len(notes)>4000 or any(ord(c)<32 and c not in '\n\t\r' for c in notes):raise ValueError('更新说明无效')
        support=item.get('supports_updater',False)
        if type(support) is not bool:raise ValueError('版本更新能力标记无效')
        result.append(Release(series,version,order,target,url,size,digest.lower(),notes,support))
    return result


def select_release(releases,version=LAUNCHER_VERSION,order=LAUNCHER_UPDATE_ORDER):
    candidates=[r for r in releases if r.series==edition(version) and r.platform=='windows-x64']
    latest=max(candidates,key=lambda r:r.order,default=None)
    return latest if latest and latest.order>order and latest.version!=version else None


def fetch_releases(*,proxy=None):
    request=urllib.request.Request(MANIFEST_URL+'?ref=main&fresh='+str(time.time_ns()),headers={
        'Accept':'application/vnd.github.raw+json','Cache-Control':'no-cache, no-store','User-Agent':'OnionMinecraftLauncher-Updater'})
    body=fetch_public(request,limit=MAX_MANIFEST,timeout=12,proxy=proxy)
    return parse_manifest(json.loads(body.decode('utf-8-sig')))


def available_releases(releases,version=LAUNCHER_VERSION):
    # Manual selection may cross editions; automatic selection never does.
    return sorted((r for r in releases if r.platform=='windows-x64'),key=lambda r:(r.series==edition(version),r.order),reverse=True)


def check_update(*,proxy=None,version=LAUNCHER_VERSION,order=LAUNCHER_UPDATE_ORDER):
    return select_release(fetch_releases(proxy=proxy),version,order)


def can_install():
    return os.name=='nt' and getattr(sys,'frozen',False) and platform.machine().lower() in ('amd64','x86_64')


def verify_executable(path,release):
    path=Path(path)
    if not path.is_file() or path.stat().st_size!=release.size:raise ValueError('更新文件大小校验失败')
    with path.open('rb') as source:
        if hashlib.file_digest(source,'sha256').hexdigest()!=release.sha256:raise ValueError('更新文件 SHA256 校验失败')
        source.seek(0)
        if source.read(2)!=b'MZ':raise ValueError('更新文件不是 Windows 程序')
        source.seek(0x3c);offset=source.read(4)
        if len(offset)!=4:raise ValueError('更新程序格式无效')
        offset=struct.unpack('<I',offset)[0]
        if offset>release.size-6:raise ValueError('更新程序格式无效')
        source.seek(offset)
        if source.read(6)!=b'PE\0\0\x64\x86':raise ValueError('更新程序不是 Windows x64 程序')


def download_update(release,executable,downloader,job):
    # New private staging directory is on the same volume as the current EXE.
    root=Path(executable).resolve().parent
    parent=root/'.onion/updates'
    if not parent.resolve().is_relative_to(root):raise ValueError('更新缓存不能指向启动器目录以外')
    parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='pending-',dir=parent))/'update.exe'
    try:
        for direct in (False,True):
            transport=Downloader(retries=1,timeout=15,proxy=None if direct else downloader.proxy,
                speed_limit=downloader.speed_limit,use_system_proxy=not direct)
            try:
                with transport.cancellable(job.cancel,job.transferred):
                    job.emit('下载启动器 '+release.version)
                    transport.download_one(DownloadJob(release.url,stage,size=release.size,sha256=release.sha256),lambda a,b:job.emit((a,b)))
                break
            except DownloadCancelled:raise
            except DownloadError:
                if direct:raise
        if job.cancel.is_set():raise DownloadCancelled('已取消更新')
        verify_executable(stage,release)
        return stage
    except Exception:
        stage.unlink(missing_ok=True);stage.with_name(stage.name+'.part').unlink(missing_ok=True)
        try:stage.parent.rmdir()
        except OSError:pass
        raise


def _ps(value):
    return "'"+str(value).replace("'","''")+"'"


def replacement_script(executable,staged,release,pid):
    executable=Path(executable).resolve();staged=Path(staged).resolve()
    update_root=executable.parent/'.onion/updates'
    if executable.suffix.lower()!='.exe' or not staged.is_relative_to(update_root) or staged.name!='update.exe' or executable==staged or type(pid) is not int or pid<1:
        raise ValueError('更新替换路径无效')
    # No paths or commands from the remote JSON are evaluated by PowerShell.
    template='''$ErrorActionPreference='Stop'
$target=@@TARGET@@
$staged=@@STAGED@@
$backup=@@BACKUP@@
$failed=@@FAILED@@
$status=@@STATUS@@
$ready=@@READY@@
$replaced=$false
$parentExited=$false
function Start-Launcher {
    $info=[System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName=$target
    $info.WorkingDirectory=@@WORKDIR@@
    $info.UseShellExecute=$false
    $info.WindowStyle=[System.Diagnostics.ProcessWindowStyle]::Normal
    return [System.Diagnostics.Process]::Start($info)
}
try {
    [System.IO.File]::WriteAllText($ready,'{"result":"ready"}')
    $parentProcess=$null
    try { $parentProcess=[System.Diagnostics.Process]::GetProcessById(@@PARENT_PID@@) } catch {}
    if ($null -ne $parentProcess -and -not $parentProcess.WaitForExit(120000)) { throw 'Launcher did not exit' }
    $parentExited=$true
    $stream=[System.IO.File]::OpenRead($staged)
    $algorithm=[System.Security.Cryptography.SHA256]::Create()
    try { $digest=[System.BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','') }
    finally { $algorithm.Dispose(); $stream.Dispose() }
    if ([System.IO.FileInfo]::new($staged).Length -ne @@EXPECTED_SIZE@@ -or $digest -ne @@EXPECTED_HASH@@) { throw 'Update integrity check failed' }
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        try { [System.IO.File]::Replace($staged,$target,$backup); $replaced=$true; break }
        catch { if ($attempt -eq 39) { throw }; [System.Threading.Thread]::Sleep(250) }
    }
    $child=Start-Launcher
    if ($child.WaitForExit(3000) -and $child.ExitCode -ne 0) { throw 'Updated launcher failed to start' }
    [System.IO.File]::WriteAllText($status,'{"result":"success"}')
} catch {
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine([System.IO.Path]::GetDirectoryName($status),'error.txt'),$_.Exception.ToString())
    if ($replaced -and [System.IO.File]::Exists($backup)) {
        try { [System.IO.File]::Replace($backup,$target,$failed) }
        catch { [System.IO.File]::WriteAllText([System.IO.Path]::Combine([System.IO.Path]::GetDirectoryName($status),'rollback-error.txt'),$_.Exception.ToString()) }
    }
    [System.IO.File]::WriteAllText($status,'{"result":"failed"}')
    if ($parentExited -and [System.IO.File]::Exists($target)) { $null=Start-Launcher }
    exit 1
}
'''
    fields={'PARENT_PID':str(pid),'EXPECTED_SIZE':str(release.size),'EXPECTED_HASH':_ps(release.sha256),
        'TARGET':_ps(executable),'STAGED':_ps(staged),'BACKUP':_ps(staged.parent/'previous.exe'),
        'FAILED':_ps(staged.parent/'failed.exe'),
        'READY':_ps(staged.parent/'ready.json'),
        'STATUS':_ps(staged.parent/'result.json'),'WORKDIR':_ps(executable.parent)}
    return re.sub(r'@@([A-Z_]+)@@',lambda match:fields[match[1]],template)


def finish_previous_updates(executable):
    """Acknowledge one prior failure; discard successful replacement backups."""
    parent=Path(executable).resolve().parent;root=parent/'.onion/updates';failed=False
    if not root.is_dir() or root.is_symlink() or not root.resolve().is_relative_to(parent):return False
    for folder in root.glob('pending-*'):
        if folder.is_symlink() or not folder.is_dir() or not folder.resolve().is_relative_to(root.resolve()):continue
        result=folder/'result.json'
        try:
            if result.is_symlink() or not result.is_file() or result.stat().st_size>1024:continue
            state=json.loads(result.read_text(encoding='utf-8'))
            if state.get('result')=='failed':failed=True;result.unlink()
            elif state.get('result')=='success':
                for name in ('previous.exe','update.exe','ready.json','result.json'):(folder/name).unlink(missing_ok=True)
                try:folder.rmdir()
                except OSError:pass
        except (OSError,ValueError,AttributeError):continue
    return failed


def launch_replacement(executable,staged,release):
    if not can_install() or Path(executable).resolve()!=Path(sys.executable).resolve():raise RuntimeError('自动替换仅适用于 Windows 打包版启动器')
    verify_executable(staged,release)
    script=replacement_script(executable,staged,release,os.getpid())
    powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    ready=Path(staged).parent/'ready.json';ready.unlink(missing_ok=True)
    process=subprocess.Popen([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand',encoded],
        cwd=Path(executable).resolve().parent,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    # Never close the launcher if Windows blocked or failed to start its helper.
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        if ready.is_file():return process
        if process.poll() is not None:break
        time.sleep(.03)
    if process.poll() is None:process.terminate();process.wait(timeout=3)
    raise RuntimeError('更新辅助程序无法启动，当前启动器保持运行。请稍后重试或手动更新。')
