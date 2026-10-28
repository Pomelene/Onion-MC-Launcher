"""Bounded, streaming ZIP extraction shared by packs, natives and saves."""
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveLimits:
    members:int=100_000
    member_bytes:int=1024**3
    total_bytes:int=8*1024**3
    ratio:int=1000


DEFAULT_LIMITS=ArchiveLimits()


def validate_archive(archive,limits=DEFAULT_LIMITS):
    members=archive.infolist()
    if len(members)>limits.members:raise ValueError('压缩包文件数量超过安全上限')
    total=0;seen=set()
    for info in members:
        key=info.filename.replace('\\','/').rstrip('/').casefold()
        if key in seen:raise ValueError('压缩包包含重复路径')
        seen.add(key)
        if info.flag_bits&1 or stat.S_ISLNK(info.external_attr>>16):
            raise ValueError('不支持加密文件或符号链接')
        if info.file_size<0 or info.file_size>limits.member_bytes:raise ValueError('压缩包单文件大小超过安全上限')
        total+=info.file_size
        if total>limits.total_bytes:raise ValueError('压缩包展开大小超过安全上限')
        if info.file_size>1024**2 and info.file_size>max(1,info.compress_size)*limits.ratio:
            raise ValueError('压缩包压缩率异常')


def read_member(archive,name,limit=16*1024**2):
    info=archive.getinfo(name)
    if info.file_size>limit:raise ValueError('压缩包元数据过大')
    with archive.open(info) as source:
        value=source.read(limit+1)
    if len(value)>limit:raise ValueError('压缩包元数据过大')
    return value


def copy_member(archive,info,destination,*,cancel_event=None,limit=1024**3,digest=None):
    from .download import DownloadCancelled
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    if info.file_size>limit:raise ValueError('解压内容超过安全上限')
    if info.file_size>max(0,shutil.disk_usage(destination.parent).free-64*1024**2):
        raise ValueError('磁盘空间不足，已停止解压')
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent,prefix='.onion-extract-',delete=False) as output:
            temporary=Path(output.name);done=0
            with archive.open(info) as source:
                while True:
                    if cancel_event is not None and cancel_event.is_set():raise DownloadCancelled('已取消解压')
                    block=source.read(65536)
                    if not block:break
                    done+=len(block)
                    if done>limit or done>info.file_size:raise ValueError('解压内容超过安全上限')
                    output.write(block)
                    if digest is not None:digest.update(block)
            if done!=info.file_size:raise ValueError('解压内容长度与声明不符')
        if cancel_event is not None and cancel_event.is_set():raise DownloadCancelled('已取消解压')
        from .storage import _replace
        _replace(temporary,destination)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
