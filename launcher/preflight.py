"""Local launch checks; no network, account refresh, game execution or repair."""
import os,shlex,shutil,tempfile
from pathlib import Path
from .mod_audit import Issue,audit


def inspect(repo,vid,settings,*,write_probe=False):
    issues=[]
    try:
        repo.assert_idle(vid);run=repo.run_dir(vid)
        # Non-isolated instances legitimately use the game root itself.
        # The write boundary deliberately rejects the root, so validate a child.
        repo.assert_writable(run/'.onion-preflight-probe')
    except (OSError,ValueError,RuntimeError) as error:return [Issue('error','directory',str(error))]
    required=0;loader='';loader_version='';game=vid
    try:
        from .modpack import _base_version,_detect_loader
        rv=repo.resolver.resolve(vid);required=rv.java_major
        game=_base_version(repo,vid);loader,loader_version=_detect_loader(repo,vid)
    except Exception as error:issues.append(Issue('warning','version','本地版本信息未完整解析，启动时将尝试补全：'+str(error)[:180]))
    nearest=run
    while not nearest.exists() and nearest!=nearest.parent:nearest=nearest.parent
    try:
        free=shutil.disk_usage(nearest).free
        if free<256*1024**2:issues.append(Issue('error','disk','游戏目录所在磁盘可用空间不足 256 MiB，请先清理空间'))
        elif free<2*1024**3:issues.append(Issue('warning','disk','可用空间不足 2 GiB，补全资源或写入存档时可能失败'))
        if write_probe:
            # Check the closest existing directory without creating a half-installed instance.
            with tempfile.TemporaryFile(dir=nearest) as output:output.write(b'Onion preflight');output.flush()
        elif not os.access(nearest,os.W_OK):issues.append(Issue('error','writable','当前账户可能没有游戏目录的写入权限'))
    except OSError as error:issues.append(Issue('error','writable','无法访问或写入游戏目录：'+str(error)[:180]))
    low=int(settings.get('min_memory') or 512);high=int(settings.get('max_memory') or 2048)
    if low>high:issues.append(Issue('error','memory','最小内存大于最大内存，请修改实例或全局设置'))
    try:
        for key in ('jvm_args','game_args'):shlex.split(settings.get(key) or '')
    except ValueError:issues.append(Issue('error','arguments','启动参数含有未闭合的引号'))
    java_major=''
    if settings.get('java_path'):
        from .java import probe_java
        java=probe_java(Path(settings['java_path']))
        if not java:issues.append(Issue('error','java','指定的 Java 无法执行，请在 Java 管理中重新选择'))
        else:
            java_major=str(java.major)
            if required and java.major<required:issues.append(Issue('error','java',f'该游戏要求 Java {required} 或更高，当前为 Java {java.major}'))
            if java.bits==32 and high>1400:issues.append(Issue('warning','java_memory','32 位 Java 使用较大堆内存可能无法启动，建议选择 64 位 Java'))
    else:issues.append(Issue('info','java',f'启动时自动选择兼容 Java'+(f'（游戏要求 {required}）' if required else '')))
    mods=audit(run/'mods',game,loader,loader_version,java_major)
    if (run/'config/fabric_loader_dependencies.json').exists():
        for item in mods:
            if item.code in ('missing','version','conflict'):item.severity='warning'
        issues.append(Issue('warning','overrides','检测到 Fabric 依赖覆盖文件；依赖检查仅供参考，以加载器实际解析为准'))
    issues.extend(mods)
    try:
        from .mod_plan import pending_changes
        if pending_changes(repo,run/'mods'):issues.append(Issue('error','interrupted','此模组目录有未完成变更，请先在模组检查页恢复中断变更（包括共用目录的其他实例）'))
    except (OSError,ValueError,KeyError,TypeError) as error:issues.append(Issue('error','journal','无法确认模组事务状态：'+str(error)[:180]))
    return issues
