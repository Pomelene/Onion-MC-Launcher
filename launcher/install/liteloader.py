"""Install a standalone LiteLoader profile from HMCL's public version index."""
import json
import re
from urllib.parse import urlsplit
from ..download import DownloadError
from ..libraries import maven_path
from ..safety import write_text

INDEX='https://raw.githubusercontent.com/HMCL-dev/HMCL/main/HMCLCore/src/main/resources/assets/liteloader/versions.json'

def list_versions(downloader,game):
    data=downloader.fetch_json(INDEX)
    if not isinstance(data,list):raise DownloadError('LiteLoader 版本列表无效')
    return [item for item in reversed(data) if isinstance(item,dict) and item.get('gameVersion')==game and isinstance(item.get('version'),str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',item['version'])]

def install_loader(repo,game,version,on_stage=None,on_progress=None):
    if on_stage:on_stage('查询 LiteLoader 版本')
    entry=next((item for item in list_versions(repo.downloader,game) if item['version']==version),None)
    if not entry:raise DownloadError('没有适用的 LiteLoader 版本')
    url=entry.get('url','');parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ('dl.liteloader.com','repo.mumfrey.com') or parsed.username or parsed.password:raise DownloadError('LiteLoader 下载地址无效')
    libraries=entry.get('libraries') or []
    if not isinstance(libraries,list) or len(libraries)>64 or any(not isinstance(item,dict) or not isinstance(item.get('name'),str) for item in libraries):raise DownloadError('LiteLoader 依赖信息无效')
    libraries=[dict(item) for item in libraries]
    for item in libraries:
        if item.get('url')=='http://repo.maven.apache.org/maven2/':item['url']='https://repo.maven.apache.org/maven2/'
    base=repo.install(game,on_stage,on_progress)
    if not base.minecraft_args:raise DownloadError('此 Minecraft 版本不支持 LiteLoader 的旧版启动参数')
    name='com.mumfrey:liteloader:'+version
    own={'name':name,'downloads':{'artifact':{'path':maven_path(name),'url':url}}}
    ident='liteloader-'+version+'-'+game
    profile={'id':ident,'inheritsFrom':game,'mainClass':'net.minecraft.launchwrapper.Launch',
             'minecraftArguments':base.minecraft_args+' --tweakClass com.mumfrey.liteloader.launch.LiteLoaderTweaker',
             'libraries':libraries+[own],'onionLoaderComponent':{'kind':'liteloader','version':version}}
    target=repo.version_dir(ident);repo.assert_writable(target);target.mkdir(parents=True,exist_ok=True)
    write_text(target/(ident+'.json'),json.dumps(profile,ensure_ascii=False,indent=2))
    return ident
