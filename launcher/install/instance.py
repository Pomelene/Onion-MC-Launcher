"""Publish one complete game instance; intermediate versions stay in staging."""
import copy,json,shutil,tempfile,uuid
from pathlib import Path
from ..download import DownloadCancelled
from ..safety import component


def next_instance_id(repo,name):
    name=component(name);ident=name;number=2
    while repo.version_dir(ident).exists():ident=f'{name}-{number}';number+=1
    return ident


def install_instance(repo,game,kind,loader_version,target_id,request_id=None,on_stage=None,on_progress=None,cancel=None):
    from ..repository import GameRepository
    from ..version import VersionResolver
    from ..modpack import _standalone_profile
    request_id=request_id or uuid.uuid4().hex;target=repo.assert_writable(repo.version_dir(component(target_id)))
    if target.exists():
        profile=target/f'{target_id}.json'
        if profile.is_file() and json.loads(profile.read_text(encoding='utf-8')).get('onionInstallRequest')==request_id:return target_id
        raise FileExistsError('实例目录已存在：'+target_id)
    if kind not in ('vanilla','fabric','legacyfabric','quilt','forge','neoforge','optifine'):raise ValueError('不支持的加载器')
    def check():
        if cancel is not None and cancel.is_set():raise DownloadCancelled('安装已取消')
    check();cache=repo.assert_writable(repo.game_dir/'.onion/install');cache.mkdir(parents=True,exist_ok=True)
    from ..storage import _hide
    _hide(cache.parent)
    with tempfile.TemporaryDirectory(dir=cache,prefix='instance-',ignore_cleanup_errors=True) as temporary:
        config=copy.copy(repo.config);config.data=dict(repo.config.data)
        staged=GameRepository(config);staged.versions_dir=Path(temporary)/'versions';staged.resolver=VersionResolver(staged.versions_dir);staged._manifest=repo._manifest
        # Copy runtime metadata and client files only, never mods/saves/options.
        seeds=[game]
        if kind in ('fabric','legacyfabric','quilt') and loader_version:seeds.append(f'{kind}-loader-{loader_version}-{game}')
        seen=set()
        while seeds:
            ident=seeds.pop()
            if ident in seen:continue
            seen.add(ident);source=repo.resolver.json_path(ident)
            if not source.is_file():continue
            raw=repo.resolver.load_raw(ident);folder=staged.version_dir(ident);folder.mkdir(parents=True,exist_ok=True)
            jar=source.with_suffix('.jar')
            if jar.is_file():shutil.copy2(jar,folder/jar.name)
            from ..components import component_info
            if ident==game and component_info(repo,ident)[1]:continue
            (folder/f'{ident}.json').write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
            for parent in (raw.get('inheritsFrom'),raw.get('jar')):
                if parent and parent!=ident:seeds.append(parent)
        with staged.downloader.cancellable(cancel,getattr(getattr(repo.downloader,'_local',None),'on_bytes',None)):
            if kind=='vanilla':result=game
            elif kind in ('fabric','legacyfabric','quilt'):
                from .fabric import install_loader
                result=install_loader(staged,game,loader_version or None,kind,on_stage)
            elif kind in ('forge','neoforge'):
                from .forge import install_forge
                result=install_forge(staged,game,kind,loader_version,on_stage,on_progress)
            else:
                from .optifine import install,pick_edition
                from ..java import resolve_java
                base=staged.install(game,on_stage,on_progress)
                java=resolve_java(base.java_major or 8,config.get('java_path'),staged.downloader,on_stage,on_progress)
                if not java:raise RuntimeError('安装 OptiFine 需要可用的 Java')
                edition=pick_edition(staged.downloader,game,loader_version)
                if edition is None:raise RuntimeError('所选 OptiFine 版本已不可用')
                result=install(staged,game,edition,java_path=str(java.path),on_stage=on_stage,on_progress=on_progress)
            staged.install(result,on_stage,on_progress);check()
            raw=_standalone_profile(staged,result,game);source=staged.version_dir(result)
            # Normalize the complete profile/client pair to the one chosen ID.
            raw['id']=target_id;raw['onionInstallRequest']=request_id
            old_json=source/f'{result}.json';old_jar=source/f'{result}.jar'
            if result!=target_id:
                old_json.unlink();old_jar.rename(source/f'{target_id}.jar')
            (source/f'{target_id}.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
            check();repo.versions_dir.mkdir(parents=True,exist_ok=True)
            if target.exists():raise FileExistsError('安装期间目标目录被占用')
            source.rename(target)
    repo.invalidate_library_cache()
    return target_id
