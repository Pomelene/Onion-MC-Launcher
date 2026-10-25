"""Bounded local dependency inspection. Unknown predicates are never hard errors.

Fabric metadata: https://docs.fabricmc.net/develop/loader/fabric-mod-json
This is a preflight aid, not a replacement for the actual loader's resolver.
"""
import io,json,re,zipfile,tomllib
from dataclasses import dataclass,field
from pathlib import Path


def _version(text):
    match=re.fullmatch(r'(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.-]*))?(?:\+[0-9A-Za-z.-]+)?',str(text))
    if not match:return None
    numbers=tuple(int(n) for n in match[1].split('.'));numbers=numbers+(0,)*max(0,4-len(numbers))
    pre=tuple((0,int(p)) if p.isdigit() else (1,p.lower()) for p in match[2].split('.')) if match[2] else ()
    return numbers,match[2] is None,pre


def matches(version,rule):
    """True/False/None for supported SemVer predicates or Maven intervals."""
    if isinstance(rule,list):
        results=[matches(version,r) for r in rule]
        return True if True in results else None if None in results else False
    if not isinstance(rule,str):return None
    rule=rule.strip()
    if not rule or rule=='*':return True
    if '||' in rule:return matches(version,[r.strip() for r in rule.split('||')])
    if rule[0] in '[(':
        if rule[0]=='[' and rule.endswith(']') and ',' not in rule:return str(version)==rule[1:-1]
        m=re.fullmatch(r'([\[(])([^,]*),([^,]*)([\])])',rule)
        if not m:return None
        results=[]
        if m[2].strip():results.append(matches(version,('>=' if m[1]=='[' else '>')+m[2].strip()))
        if m[3].strip():results.append(matches(version,('<=' if m[4]==']' else '<')+m[3].strip()))
        return False if False in results else None if None in results else True
    parts=rule.split()
    if len(parts)>1:
        results=[matches(version,r) for r in parts]
        return False if False in results else None if None in results else True
    m=re.fullmatch(r'(>=|<=|>|<|=|~|\^)?(.+)',rule)
    op,wanted=m[1] or '=',m[2]
    if re.fullmatch(r'\d+(?:\.\d+)*\.[xX*]',wanted) and op=='=':
        prefix=tuple(int(n) for n in wanted.split('.')[:-1]);v=_version(version)
        return v[0][:len(prefix)]==prefix if v else None
    a,b=_version(version),_version(wanted)
    if a is None or b is None:return str(version)==wanted if op=='=' else None
    if op in ('~','^'):
        # Fabric's operators compare the first two / first components, including
        # zero-major versions; they are not npm's special zero-major caret rule.
        count=2 if op=='~' else 1
        return a>=b and a[0][:count]==b[0][:count]
    return {'=':a==b,'>':a>b,'<':a<b,'>=':a>=b,'<=':a<=b}[op]


@dataclass
class Metadata:
    path: Path
    id: str
    version: str
    loader: str
    requires: dict=field(default_factory=dict)
    conflicts: dict=field(default_factory=dict)
    aliases: list=field(default_factory=list)
    uncertain: bool=False
    depth: int=0
    parents: tuple=()
    environment: str='*'
    runtime: bool=False


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    path: str=''
    dependency: str=''


class InspectionLimit(ValueError):pass


def inspect_jar(path,preferred_loader=''):
    result=[];budget=[128*1024*1024,512]
    def read(zf,name,limit=256*1024):
        info=zf.getinfo(name)
        if info.file_size>limit or budget[0]<info.file_size:raise InspectionLimit('模组元数据或内嵌文件超过检查上限')
        budget[0]-=info.file_size
        return zf.read(info)
    def visit(source,depth=0,parents=()):
        if depth>8 or budget[1]<=0:raise InspectionLimit('模组内嵌层级或数量超过检查上限')
        budget[1]-=1
        start=len(result)
        with zipfile.ZipFile(source) as zf:
            if len(zf.infolist())>100000:raise InspectionLimit('模组包含过多文件')
            names=set(zf.namelist());nested=[]
            native_toml=any(n in names for n in ('META-INF/neoforge.mods.toml','META-INF/mods.toml'))
            if 'fabric.mod.json' in names and not (preferred_loader in ('forge','neoforge') and native_toml) and not (preferred_loader=='quilt' and 'quilt.mod.json' in names):
                data=json.loads(read(zf,'fabric.mod.json').decode('utf-8-sig'),strict=False)
                result.append(Metadata(Path(path),str(data.get('id','')),str(data.get('version','')),'fabric',data.get('depends') or {},data.get('breaks') or {},data.get('provides') or [],environment=data.get('environment','*')))
                if data.get('environment')=='server':
                    result[-1].depth=depth;result[-1].parents=parents;return
                nested=[j.get('file','') for j in data.get('jars',[]) if isinstance(j,dict)]
            elif 'quilt.mod.json' in names:
                data=json.loads(read(zf,'quilt.mod.json').decode('utf-8-sig'),strict=False);loader=data.get('quilt_loader') or {}
                deps={};uncertain=False
                for dep in loader.get('depends') or []:
                    if not isinstance(dep,dict) or dep.get('unless') is not None:uncertain=True;continue
                    if not dep.get('optional') and isinstance(dep.get('id'),str):deps[dep['id']]=dep.get('versions','*')
                base=Metadata(Path(path),str(loader.get('id','')),str(loader.get('version','')),'quilt',deps,uncertain=uncertain);result.append(base)
                for provided in loader.get('provides',[]):
                    if isinstance(provided,str):base.aliases.append(provided)
                    elif isinstance(provided,dict):result.append(Metadata(Path(path),str(provided.get('id','')),str(provided.get('version') or loader.get('version','')),'quilt'))
                nested=[j.get('file','') if isinstance(j,dict) else j for j in loader.get('jars',[])]
            else:
                file=next((name for name in ('META-INF/neoforge.mods.toml','META-INF/mods.toml') if name in names),None)
                if file:
                    data=tomllib.loads(read(zf,file).decode('utf-8'));loader='neoforge' if 'neoforge' in file else 'forge'
                    for mod in data.get('mods',[]):
                        key=mod.get('modId','');deps={};conflicts={}
                        for dep in (data.get('dependencies') or {}).get(key,[]):
                            if str(dep.get('side','BOTH')).upper()=='SERVER':continue
                            if dep.get('type')=='incompatible':conflicts[dep.get('modId','')]=dep.get('versionRange','*')
                            elif dep.get('mandatory',dep.get('type')=='required'):deps[dep.get('modId','')]=dep.get('versionRange','*')
                        result.append(Metadata(Path(path),key,str(mod.get('version','')),'forge' if loader=='forge' else 'neoforge',deps,conflicts))
            own=result[start].id if len(result)>start else ''
            for item in result[start:]:item.depth=depth;item.parents=parents
            for name in nested:
                if not isinstance(name,str) or name not in names:continue
                visit(io.BytesIO(read(zf,name,32*1024*1024)),depth+1,parents+((own,) if own else ()))
    visit(path)
    for item in result:
        if not isinstance(item.requires,dict) or not isinstance(item.conflicts,dict) or not isinstance(item.aliases,list):raise ValueError('依赖元数据格式无效')
    return result


def runtime_modules(repo,vid):
    result=[]
    for lib in repo.resolver.resolve(vid).libraries:
        parts=lib.name.split(':')
        if len(parts)>=3 and (parts[0],parts[1]) in (('net.fabricmc','fabric-loader'),('org.quiltmc','quilt-loader')):
            path,_=repo.resolve_library_file(lib)
            if path:result.append(path)
    return result


def audit(mods_dir,game='',loader='',loader_version='',java='',*,runtime_mods=()):
    mods_dir=Path(mods_dir);metadata=[];issues=[]
    for path in sorted(p for p in mods_dir.iterdir() if p.is_file() and p.suffix.lower() in ('.jar','.zip')) if mods_dir.is_dir() else []:
        if path.is_symlink():issues.append(Issue('warning','linked','跳过链接文件',str(path)));continue
        try:
            entries=inspect_jar(path,loader);metadata.extend(m for m in entries if m.environment!='server')
            if not entries:issues.append(Issue('warning','unknown','无法完整识别模组元数据：'+path.name,str(path)))
            if any(m.uncertain for m in entries):issues.append(Issue('warning','unsupported',path.name+' 包含条件或组合依赖，需由加载器进一步解析',str(path)))
        except InspectionLimit as error:issues.append(Issue('warning','unsupported',path.name+' · '+str(error),str(path)))
        except (OSError,ValueError,KeyError,TypeError,AttributeError,zipfile.BadZipFile,tomllib.TOMLDecodeError) as error:
            issues.append(Issue('error','metadata','模组损坏或元数据无效：'+path.name+' · '+str(error)[:160],str(path)))
    for path in runtime_mods:
        try:
            entries=inspect_jar(path,loader)
            for meta in entries:meta.runtime=True
            metadata.extend(m for m in entries if m.environment!='server')
        except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile):issues.append(Issue('warning','unsupported','无法完整读取加载器内嵌组件',str(path)))
    # A bundled JAR is an alternative candidate, not another mandatory root mod.
    # Select shared nested providers against the requirements of active parents.
    roots=[m for m in metadata if m.depth==0];selected={};root_ids={m.id for m in roots}
    rank=lambda m:(_version(m.version) is not None,_version(m.version) or ((0,0,0,0),False,()),m.version)
    for item in roots:
        if item.id not in selected or rank(item)>rank(selected[item.id]):selected[item.id]=item
    for key in root_ids:
        items=[m for m in roots if m.id==key and not m.runtime]
        if len({str(m.path) for m in items})>1:issues.append(Issue('error','duplicate','重复的顶层模组 ID：'+key+' · '+'、'.join(sorted({m.path.name for m in items})),dependency=key))
    def provider_map(items):
        result={}
        for meta in items:
            for key in [meta.id,*meta.aliases]:
                if isinstance(key,str) and key:result.setdefault(key,[]).append(meta)
        return result
    signatures=set()
    for _ in range(min(len(metadata)+1,512)):
        signature=tuple(sorted((key,m.version,str(m.path)) for key,m in selected.items()))
        if signature in signatures:break
        signatures.add(signature);constraints={};current=provider_map(selected.values());changed=False
        for meta in selected.values():
            for dep,rule in meta.requires.items():constraints.setdefault(dep,[]).append(rule)
        for dep in constraints:
            if any(m.depth==0 for m in current.get(dep,[])):continue
            candidates=[m for m in metadata if m.depth and dep in [m.id,*m.aliases]]
            viable=[m for m in candidates if all(matches(m.version,rule) is not False for key in [m.id,*m.aliases] if isinstance(key,str) for rule in constraints.get(key,[]))]
            if viable:
                chosen=max(viable,key=rank)
                for parent in chosen.parents:
                    if parent not in selected:
                        ancestors=[m for m in metadata if m.path==chosen.path and m.id==parent]
                        if ancestors:selected[parent]=max(ancestors,key=rank);changed=True
                if chosen.id not in selected or selected[chosen.id] is not chosen:selected[chosen.id]=chosen;changed=True
        if not changed:break
    providers=provider_map(selected.values())
    incomplete=any(i.code in ('unknown','unsupported','linked') for i in issues)
    builtins={'minecraft':game,'java':java}
    if loader:builtins[{'fabric':'fabricloader','quilt':'quilt_loader'}.get(loader,loader)]=loader_version
    if loader=='quilt':builtins['fabricloader']=''
    for meta in selected.values():
        if loader and meta.loader!=loader and not (loader=='quilt' and meta.loader=='fabric'):
            issues.append(Issue('error','loader',f'{meta.path.name} 使用 {meta.loader}，当前为 {loader}',str(meta.path)));continue
        for dep,rule in meta.requires.items():
            if dep in builtins and not builtins[dep]:continue
            available=[m.version for m in providers.get(dep,[])] or ([builtins[dep]] if dep in builtins else [])
            if not available:
                candidates=[m for m in metadata if m.depth and dep in [m.id,*m.aliases]]
                if candidates:
                    issues.append(Issue('error','version',f'{meta.id} 要求 {dep} {rule}，没有一个内嵌候选同时满足当前依赖要求（候选：'+', '.join(sorted({m.version for m in candidates}))+')',str(meta.path),dep));continue
                issues.append(Issue('warning' if incomplete else 'error','missing',f'{meta.id} '+('尚未确认前置 ' if incomplete else '缺少 ')+f'{dep}（要求 {rule}）'+('；部分模组未完整解析' if incomplete else ''),str(meta.path),dep));continue
            values=[matches(v,rule) if v else None for v in available]
            if True not in values:
                unknown=None in values
                issues.append(Issue('warning' if unknown else 'error','unverified' if unknown else 'version',f'{meta.id} 要求 {dep} {rule}，当前 '+', '.join(available)+( '；需由加载器进一步核对' if unknown else ''),str(meta.path),dep))
        for dep,rule in meta.conflicts.items():
            if any(matches(m.version,rule) is True for m in providers.get(dep,[])):
                issues.append(Issue('error','conflict',f'{meta.id} 声明与 {dep} {rule} 不兼容',str(meta.path),dep))
    return issues
