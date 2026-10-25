"""Explicit Modrinth dependency plans and recoverable, verified mod changes."""
import json,os,shutil,uuid
from pathlib import Path
from urllib.parse import quote,urlsplit
from .download import DownloadJob,DownloadCancelled
from .safety import child,component,contained,write_text
from .mods import scan_mods,mod_sha1,MODRINTH_API


def _cancel(job):
    if job and job.cancel.is_set():raise DownloadCancelled('模组操作已取消')


def snapshot(folder):
    folder=Path(folder)
    return {p.name:mod_sha1(p) for p in sorted(folder.iterdir()) if p.is_file() and p.name.lower().endswith(('.jar','.zip','.jar.disabled','.zip.disabled'))} if folder.exists() else {}


def identify(downloader,folder,job=None):
    found={};unknown=[]
    for info in scan_mods(Path(folder)):
        if not info.enabled:continue
        _cancel(job)
        if job:job.emit('识别 '+info.path.name)
        try:
            digest=mod_sha1(info.path)
            data=downloader.fetch_json(f'{MODRINTH_API}/version_file/{digest}?algorithm=sha1')
            if not isinstance(data,dict) or not data.get('project_id'):raise ValueError('未收录')
            pid=data['project_id']
            if pid in found:raise ValueError('同一项目存在多个启用版本，请先处理重复模组')
            found[pid]={'path':info.path,'version':data}
        except DownloadCancelled:raise
        except Exception as error:unknown.append(info.path.name+' · '+str(error)[:120])
    return found,unknown


def compatible(version,game,loader):
    return (not game or game in (version.get('game_versions') or [])) and (not loader or loader.lower() in [str(v).lower() for v in version.get('loaders') or []])


def updates(downloader,folder,game,loader,job=None,allow_preview=False):
    installed,unknown=identify(downloader,folder,job);result=[]
    for pid,item in installed.items():
        _cancel(job)
        versions=downloader.fetch_json(f'{MODRINTH_API}/project/{quote(pid,safe="")}/version')
        current=item['version'];date=current.get('date_published','')
        candidates=[v for v in versions if compatible(v,game,loader) and (allow_preview or v.get('version_type')=='release') and v.get('files')]
        candidates.sort(key=lambda v:v.get('date_published',''),reverse=True)
        if candidates and date and candidates[0].get('date_published','')>date and candidates[0].get('id')!=current.get('id'):
            result.append({'path':item['path'],'current':current,'latest':candidates[0]})
    return result,unknown


def build_plan(downloader,folder,roots,game,loader,job=None,optional=False):
    folder=Path(folder);before=snapshot(folder);installed,unknown=identify(downloader,folder,job)
    from .mod_audit import audit
    if any(i.code=='duplicate' for i in audit(folder,game,loader)):raise ValueError('请先处理重复模组 ID，再生成安装或更新方案')
    chosen={};reasons={};conflicts=[]
    def visit(version,reason):
        _cancel(job)
        pid=version.get('project_id');vid=version.get('id')
        if not isinstance(pid,str) or not isinstance(vid,str):raise ValueError('版本缺少项目或版本标识')
        if not compatible(version,game,loader):raise ValueError('依赖版本不匹配目标游戏或加载器：'+pid)
        if pid in chosen:
            if chosen[pid]['id']!=vid:raise ValueError('多个模组要求不同的依赖版本：'+pid+'；请分别调整版本后重试')
            reasons[pid].add(reason);return
        if len(chosen)>=256:raise ValueError('依赖数量超过安全上限')
        chosen[pid]=version;reasons[pid]={reason}
        for dep in version.get('dependencies') or []:
            kind=dep.get('dependency_type');dp=dep.get('project_id');dv=dep.get('version_id')
            if kind=='incompatible':conflicts.append((dp,dv));continue
            if kind!='required' and not (optional and kind=='optional'):continue
            if not dp and not dv:raise ValueError('存在无法自动获取的外部依赖：'+str(dep.get('file_name') or pid))
            if dv:
                target=downloader.fetch_json(f'{MODRINTH_API}/version/{quote(str(dv),safe="")}')
                if dp and target.get('project_id')!=dp:raise ValueError('依赖项目与固定版本不一致')
            elif dp in reserved:target=reserved[dp]
            elif dp in chosen:target=chosen[dp]
            elif dp in installed and compatible(installed[dp]['version'],game,loader):target=installed[dp]['version']
            else:
                available=downloader.fetch_json(f'{MODRINTH_API}/project/{quote(str(dp),safe="")}/version')
                choices=[v for v in available if compatible(v,game,loader) and v.get('version_type')=='release' and v.get('files')]
                choices.sort(key=lambda v:v.get('date_published',''),reverse=True)
                if not choices:raise ValueError('没有可用的兼容正式版依赖：'+str(dp))
                target=choices[0]
            visit(target,pid+('（可选）' if kind=='optional' else '（必需）'))
    # Reserve explicitly selected versions first, so optional traversal cannot silently replace them.
    reserved={v.get('project_id'):v for v in roots}
    if len(reserved)!=len(roots):raise ValueError('同一项目只能选择一个版本')
    for version in roots:visit(version,'用户选择')
    for pid,dv in conflicts:
        active=chosen.get(pid) or (installed.get(pid) or {}).get('version')
        if dv and not pid:
            active=next((v for v in list(chosen.values())+[i['version'] for i in installed.values()] if v.get('id')==dv),None)
        if active and (not dv or active.get('id')==dv):raise ValueError('所选方案声明与已安装项目不兼容：'+str(pid or dv))
    entries=[];names=set()
    for pid,version in chosen.items():
        old=installed.get(pid);same=bool(old and old['version'].get('id')==version['id'])
        files=version.get('files') or [];file=next((f for f in files if f.get('primary')),files[0] if files else None)
        if not file:raise ValueError('版本没有可下载文件：'+pid)
        name=component(file['filename'])
        if not name.lower().endswith('.jar'):raise ValueError('模组方案只接受 JAR 文件')
        digest=(file.get('hashes') or {}).get('sha1','')
        if len(digest)!=40 or any(c not in '0123456789abcdef' for c in digest.lower()):raise ValueError('缺少有效文件校验值')
        if urlsplit(file['url']).scheme!='https':raise ValueError('模组下载必须使用 HTTPS')
        if not isinstance(file.get('size'),int) or not 0<file['size']<=1024**3:raise ValueError('模组大小无效')
        target=child(folder,name)
        if name.casefold() in names:raise ValueError('多个项目使用相同文件名：'+name)
        names.add(name.casefold())
        if target.exists() and not same and (not old or target!=old['path']):raise FileExistsError('文件名已被占用：'+name)
        entries.append({'project':pid,'version':version,'file':file,'old':old['path'].name if old else '',
                        'action':'保留' if same else '更新' if old else '安装','reasons':sorted(reasons[pid])})
    if snapshot(folder)!=before:raise RuntimeError('分析期间模组目录发生变化，请重新生成方案')
    return {'id':uuid.uuid4().hex,'before':before,'entries':entries,'unknown':unknown,'game':game,'loader':loader}


def apply_plan(repo,vid,plan,job=None):
    repo.assert_idle(vid);folder=repo.run_dir(vid)/'mods';repo.assert_writable(folder);folder.mkdir(parents=True,exist_ok=True)
    if snapshot(folder)!=plan['before']:raise RuntimeError('模组目录已变化，请重新生成方案')
    entries=[e for e in plan['entries'] if e['action']!='保留']
    if not entries:return None
    stage=child(repo.game_dir/'.onion/mod-changes',plan.get('id') or uuid.uuid4().hex);repo.assert_writable(stage);stage.mkdir(parents=True,exist_ok=True)
    incoming=stage/'incoming';backup=stage/'backup'
    if (stage/'journal.json').exists():
        previous=json.loads((stage/'journal.json').read_text(encoding='utf-8'))
        if previous.get('status') not in ('not_applied','preparing','rolled_back'):raise RuntimeError('此方案已经应用或需要先恢复中断变更')
    incoming.mkdir(exist_ok=True);backup.mkdir(exist_ok=True)
    if any(backup.iterdir()):raise RuntimeError('方案仍有原文件备份，请先恢复中断变更')
    journal={'status':'preparing','version':vid,'folder':str(folder.relative_to(repo.game_dir)),'old':{},'new':{}}
    def save():write_text(stage/'journal.json',json.dumps(journal,ensure_ascii=False,indent=2))
    save()
    try:
        for i,entry in enumerate(entries):
            _cancel(job);file=entry['file'];target=child(incoming,file['filename'])
            if job:job.emit('下载 '+file['filename'])
            repo.downloader.download_one(DownloadJob(file['url'],target,sha1=file['hashes']['sha1'],size=file['size']))
            if mod_sha1(target)!=file['hashes']['sha1']:raise ValueError('下载校验失败')
            journal['new'][target.name]=file['hashes']['sha1']
            if entry['old']:journal['old'][entry['old']]=plan['before'][entry['old']]
            if job:job.emit((i+1,len(entries)))
        _cancel(job);repo.assert_idle(vid)
        if snapshot(folder)!=plan['before']:raise RuntimeError('下载期间模组目录已变化，未应用方案')
        # Inspect the proposed combined directory without changing the live instance.
        proposed=stage/'proposed';proposed.mkdir(exist_ok=True)
        for file in proposed.iterdir():
            contained(file,stage)
            if not file.is_file():raise ValueError('临时检查目录包含意外子目录')
            file.unlink()
        def link(source,target):
            try:os.link(source,target)
            except OSError:shutil.copy2(source,target)
        for name in plan['before']:
            if name not in journal['old'] and name.lower().endswith(('.jar','.zip')):link(child(folder,name),child(proposed,name))
        for name in journal['new']:link(child(incoming,name),child(proposed,name))
        from .mod_audit import audit
        before_errors={(i.code,i.message) for i in audit(folder,plan['game'],plan['loader']) if i.severity=='error'}
        new_errors=[i.message for i in audit(proposed,plan['game'],plan['loader']) if i.severity=='error' and (i.code,i.message) not in before_errors]
        if new_errors:raise ValueError('下载后的依赖核对未通过：\n'+'\n'.join(new_errors[:12]))
        for file in proposed.iterdir():contained(file,stage).unlink()
        proposed.rmdir();repo.assert_idle(vid);_cancel(job)
        if snapshot(folder)!=plan['before']:raise RuntimeError('检查期间模组目录发生变化，未应用方案')
        if any(mod_sha1(child(incoming,name))!=digest for name,digest in journal['new'].items()):raise ValueError('待安装文件在校验后发生变化')
        journal['status']='applying';save();moved=[];published=[]
        try:
            for name in journal['old']:
                _cancel(job);child(folder,name).rename(child(backup,name));moved.append(name)
            for name in journal['new']:
                _cancel(job);source=child(incoming,name);target=child(folder,name)
                if target.exists():raise FileExistsError(name)
                source.rename(target);published.append(name)
        except BaseException:
            for name in reversed(published):child(folder,name).rename(child(incoming,name))
            for name in reversed(moved):child(backup,name).rename(child(folder,name))
            journal['status']='rolled_back';save();raise
        journal['status']='complete';save();return stage
    except BaseException:
        if journal['status']=='preparing':journal['status']='not_applied';save()
        raise


def undo_last(repo,vid):
    repo.assert_idle(vid);root=repo.game_dir/'.onion/mod-changes'
    candidates=[]
    for file in root.glob('*/journal.json') if root.exists() else []:
        contained(file,repo.game_dir)
        if file.stat().st_size>1024*1024:continue
        data=json.loads(file.read_text(encoding='utf-8'))
        if data.get('status')=='complete' and data.get('version')==vid:candidates.append((file.stat().st_mtime,file,data))
    if not candidates:raise ValueError('没有可撤销的已完成模组变更')
    _,file,data=max(candidates,key=lambda i:i[0]);folder=repo.run_dir(vid)/'mods';repo.assert_writable(folder)
    if folder!=child(repo.game_dir,data['folder']):raise ValueError('实例运行目录已变化，无法自动撤销')
    stage=file.parent;backup=stage/'backup';removed=stage/'undone';removed.mkdir(exist_ok=True)
    for name,digest in data['new'].items():
        if mod_sha1(child(folder,name))!=digest:raise ValueError('更新后的文件已被修改或移除，无法自动撤销：'+name)
    for name,digest in data['old'].items():
        if mod_sha1(child(backup,name))!=digest:raise ValueError('备份文件缺失或已变化：'+name)
        if name not in data['new'] and child(folder,name).exists():raise FileExistsError(name)
    moved=[];restored=[]
    try:
        for name in data['new']:child(folder,name).rename(child(removed,name));moved.append(name)
        for name in data['old']:child(backup,name).rename(child(folder,name));restored.append(name)
    except BaseException:
        for name in reversed(restored):child(folder,name).rename(child(backup,name))
        for name in reversed(moved):child(removed,name).rename(child(folder,name))
        raise
    data['status']='undone';write_text(file,json.dumps(data,ensure_ascii=False,indent=2));return len(moved)


def recover_interrupted(repo,vid):
    """Rollback an interrupted commit only after checking every affected file."""
    repo.assert_idle(vid);folder=repo.run_dir(vid)/'mods';repo.assert_writable(folder);root=repo.game_dir/'.onion/mod-changes'
    for file in root.glob('*/journal.json') if root.exists() else []:
        contained(file,repo.game_dir)
        if file.stat().st_size>1024**2:continue
        data=json.loads(file.read_text(encoding='utf-8'))
        if data.get('version')!=vid or data.get('status')!='applying':continue
        if child(repo.game_dir,data['folder'])!=folder:raise ValueError('实例目录已变化')
        backup=file.parent/'backup';restorable=[];removable=[]
        for name,digest in data['old'].items():
            source=child(backup,name);live=child(folder,name)
            if source.exists():
                if mod_sha1(source)!=digest:raise ValueError('中断备份已变化：'+name)
                restorable.append(name)
            elif mod_sha1(live)!=digest:raise ValueError('无法找到原始模组：'+name)
        for name,digest in data['new'].items():
            live=child(folder,name)
            if not live.exists():continue
            current=mod_sha1(live)
            if current==digest and (name not in data['old'] or name in restorable):removable.append(name)
            elif name not in data['old'] or current!=data['old'][name]:raise ValueError('中断后的文件已变化：'+name)
        for name in restorable:
            if child(folder,name).exists() and name not in removable:raise FileExistsError('恢复目标已占用：'+name)
        removed=file.parent/('recovered-'+uuid.uuid4().hex);removed.mkdir();moved=[];restored=[]
        try:
            for name in removable:child(folder,name).rename(child(removed,name));moved.append(name)
            for name in restorable:child(backup,name).rename(child(folder,name));restored.append(name)
        except BaseException:
            for name in reversed(restored):child(folder,name).rename(child(backup,name))
            for name in reversed(moved):child(removed,name).rename(child(folder,name))
            raise
        data['status']='rolled_back';write_text(file,json.dumps(data,ensure_ascii=False,indent=2));return len(restored)
    raise ValueError('没有需要恢复的中断变更')
