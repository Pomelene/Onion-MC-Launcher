"""Declarative, bounded service catalog over HTTPS. Remote JSON never runs code."""
import ipaddress
import json
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from .network import secure_open,validate_url

CATALOG_URL='https://api.github.com/repos/Pomelene/OnionService4THUnion/contents/webapp.json'
CONFIRMATION='本服务面向清华联盟工坊活动，我们是一个非官方非营利组织，确认要继续吗？'
MAX_BYTES=256*1024
ICONS=('folder','world','tools','package','download','upload','grid','image','schematic','home','java','skin','history','rocket')


def _presentation(source,target):
    for key in ('visible','show_urls'):
        if key in source:
            if type(source[key]) is not bool:raise ValueError('服务显示开关必须为布尔值')
            target[key]=source[key]
    if 'icon' in source:
        if source['icon'] not in ICONS:raise ValueError('不支持的服务图标')
        target['icon']=source['icon']


def read_catalog(path):
    with Path(path).open('rb') as source:
        body=source.read(MAX_BYTES+1)
    if len(body)>MAX_BYTES:raise ValueError('本地服务配置文件过大')
    return parse_catalog(json.loads(body.decode('utf-8-sig')))


def sync_catalog(path):
    """Only replace the last known-good catalog after validation and a full write."""
    catalog=fetch_catalog();path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.webapp-',suffix='.tmp',delete=False) as target:
            temporary=Path(target.name)
            target.write(json.dumps(catalog,ensure_ascii=False,indent=2).encode('utf-8'))
            target.flush();os.fsync(target.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return catalog


def web_url(value):
    validate_url(value);parsed=urllib.parse.urlsplit(value);host=parsed.hostname.lower()
    if host in ('localhost','localhost.localdomain') or host.endswith(('.localhost','.local')):
        raise ValueError('工具网址不能指向本机或局域网')
    try:
        if not ipaddress.ip_address(host).is_global:raise ValueError('工具网址不能指向本机或局域网')
    except ValueError:
        if re.fullmatch(r'[0-9.]+',host) or ':' in host:raise ValueError('工具网址无效') from None
    return value


def _text(item,key,maximum,required=True):
    value=item.get(key,'')
    if not isinstance(value,str) or len(value)>maximum or any(ord(c)<32 for c in value):raise ValueError('服务配置中的文字格式无效')
    value=value.strip()
    if required and not value:raise ValueError('服务配置缺少 '+key)
    return value


def parse_catalog(payload):
    if not isinstance(payload,dict) or type(payload.get('schema_version')) is not int or payload['schema_version'] not in (1,2):raise ValueError('不支持的服务配置版本')
    categories=payload.get('categories')
    if not isinstance(categories,list) or not 0<=len(categories)<=24:raise ValueError('服务目录数量无效')
    result=[];ids=set();count=0
    for category in categories:
        if not isinstance(category,dict):raise ValueError('服务目录格式无效')
        ident=_text(category,'id',64);title=_text(category,'title',80);description=_text(category,'description',400)
        if ident in ids:raise ValueError('服务目录标识重复')
        ids.add(ident);tools=category.get('tools')
        if not isinstance(tools,list) or not 0<=len(tools)<=32:raise ValueError('子工具数量无效')
        clean=[];tool_ids=set()
        for tool in tools:
            if not isinstance(tool,dict):raise ValueError('子工具格式无效')
            tool_id=_text(tool,'id',64)
            if tool_id in tool_ids:raise ValueError('子工具标识重复')
            tool_ids.add(tool_id)
            item={'id':tool_id,'title':_text(tool,'title',80),'description':_text(tool,'description',800),'url':web_url(_text(tool,'url',2048))}
            action=tool.get('action','web')
            if action not in ('web','external','download','copy'):raise ValueError('不支持的服务操作')
            if 'action' in tool:item['action']=action
            _presentation(tool,item)
            for key,maximum in (('button_text',32),('badge',24)):
                if key in tool:item[key]=_text(tool,key,maximum)
            if action=='download':
                from .safety import component
                filename=component(_text(tool,'filename',160));size=tool.get('size');digest=_text(tool,'sha256',64)
                if urllib.parse.urlsplit(item['url']).scheme!='https' or not filename.lower().endswith('.mrpack') or type(size) is not int or not 1<=size<=256*1024**2 or not re.fullmatch('[0-9a-fA-F]{64}',digest):
                    raise ValueError('整合包下载信息无效')
                item.update(action=action,filename=filename,size=size,sha256=digest.lower())
            clean.append(item)
            count+=1
        item={'id':ident,'title':title,'description':description,'tools':clean}
        _presentation(category,item)
        if 'layout' in category:
            if category['layout'] not in ('cards','list'):raise ValueError('不支持的服务目录布局')
            item['layout']=category['layout']
        result.append(item)
    if count>128:raise ValueError('子工具总数过多')
    result={'schema_version':payload['schema_version'],'title':_text(payload,'title',80),'categories':result}
    if 'default_category' in payload:
        selected=_text(payload,'default_category',64)
        if selected not in ids:raise ValueError('默认目录不存在')
        result['default_category']=selected
    return result


def verify_download(path,tool):
    import hashlib
    path=Path(path)
    if not path.is_file() or path.stat().st_size!=tool['size']:raise ValueError('整合包尚未下载完整，请重新下载')
    with path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    if digest!=tool['sha256']:raise ValueError('整合包校验失败，请重新下载')


def fetch_catalog():
    request=urllib.request.Request(CATALOG_URL+'?ref=main&fresh='+str(time.time_ns()),headers={
        'Accept':'application/vnd.github.raw+json','Cache-Control':'no-cache, no-store','User-Agent':'OnionMinecraftLauncher-THUnion'})
    try:
        with secure_open(request,timeout=20) as response:
            body=response.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES:raise ValueError('服务配置文件过大')
        return parse_catalog(json.loads(body.decode('utf-8-sig')))
    except (ValueError,UnicodeError) as error:raise ValueError('社团服务配置无效：'+str(error)) from None
    except Exception:raise RuntimeError('无法获取最新社团服务目录，请检查网络后重新进入') from None
