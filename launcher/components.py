"""Modify Fabric/Quilt components of one existing instance, never create profiles."""
import copy,json
from urllib.parse import quote
from .download import DownloadError,DownloadCancelled
from .libraries import Library
from .version import ResolvedVersion
from .safety import write_text


def component_info(repo,vid):
    resolved=repo.resolver.resolve(vid);kind='';version=''
    marker=repo.resolver.load_raw(vid).get('onionLoaderComponent') or {}
    if isinstance(marker,dict) and marker.get('kind')=='legacyfabric':return resolved.game_version,'legacyfabric',str(marker.get('version') or '')
    for lib in resolved.libraries:
        parts=lib.name.split(':')
        if len(parts)<3:continue
        key=tuple(parts[:2])
        if key==('net.fabricmc','fabric-loader'):kind,version='fabric',parts[2];break
        if key==('org.quiltmc','quilt-loader'):kind,version='quilt',parts[2];break
        if parts[0] in ('net.minecraftforge','net.neoforged'):kind,version=('forge' if parts[0]=='net.minecraftforge' else 'neoforge'),parts[2];break
        if parts[0].lower()=='optifine':kind,version='optifine',parts[2];break
    return resolved.game_version,kind,version


def _chain(repo,vid):
    result=[];seen=set()
    while vid:
        if vid in seen or len(seen)>=32:raise ValueError('实例继承链无效')
        seen.add(vid);path=repo.resolver.json_path(vid);raw=path.read_bytes()
        data=json.loads(raw.decode('utf-8-sig'));result.append((path,raw,data));vid=data.get('inheritsFrom')
    return result


def _cancel(event):
    if event is not None and event.is_set():raise DownloadCancelled('组件安装已取消')


def replace_loader(repo,vid,kind,version,on_stage=None,on_progress=None,cancel=None,expected_game=None):
    if kind not in ('fabric','quilt'):raise ValueError('此组件暂不支持原位安装')
    if not isinstance(version,str) or not version:raise ValueError('请选择加载器版本')
    repo.assert_idle(vid);target=repo.assert_writable(repo.resolver.json_path(vid));chain=_chain(repo,vid)
    game,current,current_version=component_info(repo,vid)
    if not game:raise ValueError('无法识别当前实例的 Minecraft 版本')
    if expected_game and game!=expected_game:raise ValueError('实例游戏版本已变化，请重新选择加载器版本')
    if current and current!=kind:raise ValueError('与当前 '+current+' 加载器不兼容')
    if any(lib.name.split(':')[0].lower() in ('net.minecraftforge','net.neoforged','optifine') for lib in repo.resolver.resolve(vid).libraries):
        raise ValueError('当前实例包含不兼容的游戏组件，不能直接安装 '+kind)
    if current_version==version:return vid
    # Editing a shared parent would also change children. Never do that silently.
    for other in repo.list_installed():
        if other==vid:continue
        try:parents=_chain(repo,other)[1:]
        except (OSError,ValueError):continue
        if any(path==target for path,_,_ in parents):
            raise ValueError('此版本被其他实例继承，不能直接修改共享加载器：'+other)
    _cancel(cancel)
    from .install.fabric import pick_loader,meta_base
    if on_stage:on_stage('获取 '+kind+' '+version)
    selected=pick_loader(repo.downloader,kind,game,version)
    if not selected:raise DownloadError('没有适用于当前游戏版本的加载器版本')
    profile=repo.downloader.fetch_json(f'{meta_base(kind)}/versions/loader/{quote(game,safe="")}/{quote(version,safe="")}/profile/json')
    libs=profile.get('libraries');main=profile.get('mainClass')
    if not isinstance(libs,list) or not all(isinstance(lib,dict) for lib in libs) or not isinstance(main,str) or not main.startswith('net.fabricmc.' if kind=='fabric' else 'org.quiltmc.'):
        raise ValueError('加载器配置不完整')
    if profile.get('inheritsFrom',game)!=game:raise ValueError('加载器的游戏版本不匹配')
    key=('net.fabricmc:fabric-loader:' if kind=='fabric' else 'org.quiltmc:quilt-loader:')+version
    if not any(lib.get('name')==key for lib in libs):raise ValueError('加载器版本与所选版本不一致')
    merged={}
    for _,_,data in reversed(chain):merged.update(copy.deepcopy(data))
    def library_key(lib):
        parts=str(lib.get('name','')).split(':');return tuple(parts[:2]+parts[3:])
    def component_library(lib):
        parts=str(lib.get('name','')).split(':');group=parts[0]
        return group in ('net.fabricmc','org.ow2.asm') or group.startswith('org.quiltmc') or parts[:2]==['org.spongepowered','mixin']
    new_keys={library_key(lib) for lib in libs}
    existing=[copy.deepcopy(lib) for _,_,data in chain for lib in data.get('libraries',[]) if not component_library(lib) and library_key(lib) not in new_keys]
    merged['libraries']=copy.deepcopy(libs)+existing
    args={}
    old_args=(chain[0][2].get('onionLoaderComponent') or {}).get('arguments') or {}
    for _,_,data in reversed(chain):
        for channel,values in (data.get('arguments') or {}).items():args.setdefault(channel,[]).extend(copy.deepcopy(values))
    new_args=profile.get('arguments') or {}
    if not isinstance(new_args,dict):raise ValueError('加载器参数无效')
    for channel in dict.fromkeys([*old_args,*new_args]):
        values=new_args.get(channel) or []
        previous=old_args.get(channel) or [];new_properties={v.split('=',1)[0] for v in values if isinstance(v,str) and v.startswith('-D')}
        args[channel]=[v for v in args.get(channel,[]) if v not in previous and not (isinstance(v,str) and v.split('=',1)[0] in new_properties)]
        args[channel].extend(copy.deepcopy(v) for v in values if v not in args[channel])
    if args:merged['arguments']=args
    resolved=repo.resolver.resolve(vid)
    merged.pop('inheritsFrom',None);merged['id']=vid;merged['mainClass']=main;merged['onionGameVersion']=game
    merged['jar']=resolved.jar_id or resolved.client_version_id or vid
    if resolved.client:merged.setdefault('downloads',{})['client']=copy.deepcopy(resolved.client)
    if resolved.asset_index:merged['assetIndex']=copy.deepcopy(resolved.asset_index)
    if resolved.java_major:merged['javaVersion']={**(merged.get('javaVersion') or {}),'majorVersion':resolved.java_major}
    if resolved.logging:merged['logging']={'client':copy.deepcopy(resolved.logging)}
    if 'hidden' not in chain[0][2]:merged.pop('hidden',None)
    merged['onionLoaderComponent']={'kind':kind,'version':version,'arguments':copy.deepcopy(profile.get('arguments') or {})}
    # Download only component libraries. Client files, assets, mods and saves stay put.
    _cancel(cancel)
    if on_stage:on_stage('准备加载器依赖')
    repo._ensure_libraries(ResolvedVersion(id=vid,libraries=[Library.from_json(lib) for lib in libs]),None,on_progress,on_stage)
    _cancel(cancel);repo.assert_idle(vid)
    if any(path.read_bytes()!=raw for path,raw,_ in chain):raise RuntimeError('下载期间实例配置发生变化，未修改加载器')
    if on_stage:on_stage('更新当前实例配置')
    write_text(target,json.dumps(merged,ensure_ascii=False,indent=2));repo.invalidate_library_cache()
    return vid
