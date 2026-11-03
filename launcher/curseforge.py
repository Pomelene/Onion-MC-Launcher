# -*- coding: utf-8 -*-
"""CurseForge 接口：整合包文件解析与下载地址。

CurseForge 官方 API 需要 key（`x-api-key`）。为便于开箱使用：
- 配置了 `curseforge_api_key` 时走官方接口；
- 否则回退到社区只读代理 `api.curse.tools`；
- 两者都不可用时给出明确提示，而不是静默失败。

下载地址：优先使用文件元数据里的 `downloadUrl`；作者关闭第三方下载时，
按 CurseForge CDN 的 `files/<id//1000>/<id%1000:0>3d/<fileName>` 规则拼接。
"""

import urllib.parse
import re
from .download import DownloadCancelled
from typing import Optional

API_BASE = "https://api.curseforge.com/v1"
PROXY_BASE = "https://api.curse.tools/v1/cf"
CDN_BASE = "https://edge.forgecdn.net/files"

#: 按 classId 决定安装目录（未列出的按 mods 处理）
CLASS_DIRS = {
    6: "mods",          # Mods
    12: "resourcepacks",  # Resource Packs
    17: "saves",        # Worlds
    6552: "shaderpacks",  # Shader Packs
}


class CurseForgeError(Exception):
    """CurseForge 接口或下载失败。"""


def cdn_url(file_id: int, filename: str) -> str:
    """按 CurseForge CDN 规则拼接下载地址。"""
    return f"{CDN_BASE}/{file_id // 1000}/{file_id % 1000:03d}/{filename}"


class CurseForgeClient:
    """最小的 CurseForge 只读客户端。"""

    def __init__(self, downloader, api_key: str = ""):
        self.downloader = downloader
        self.api_key = (api_key or "").strip()

    def _bases(self) -> list[tuple[str, dict]]:
        bases: list[tuple[str, dict]] = []
        if self.api_key:
            bases.append((API_BASE, {"x-api-key": self.api_key, "Accept": "application/json"}))
        bases.append((PROXY_BASE, {"Accept": "application/json"}))
        return bases

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        errors: list[str] = []
        for base, headers in self._bases():
            try:
                payload = self.downloader.fetch_json(base + path + query, headers=headers)
                if isinstance(payload, dict) and "data" in payload:
                    return payload
                errors.append(f"{base}: 响应格式异常")
            except DownloadCancelled:raise
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{base}: {exc}")
        hint = "" if self.api_key else "（可在设置里填写 CurseForge API Key）"
        raise CurseForgeError("CurseForge 接口不可用" + hint + "：" + "；".join(errors))

    # ------------------------------------------------------------ 查询

    def search(self,kind,query='',game_version='',loader='',index=0,page_size=20):
        classes={'mod':6,'resourcepack':12,'modpack':4471,'shader':6552}
        loaders={'forge':1,'liteloader':3,'fabric':4,'quilt':5,'neoforge':6}
        if kind not in classes:raise CurseForgeError('不支持的内容类型')
        params={'gameId':432,'classId':classes[kind],'index':max(0,int(index)),'pageSize':min(50,max(1,int(page_size)))}
        if query:params['searchFilter']=query
        if game_version:params['gameVersion']=game_version
        if loader in loaders:params['modLoaderType']=loaders[loader]
        payload=self._get('/mods/search',params)
        hits=[]
        for item in payload.get('data') or []:
            if not isinstance(item,dict) or not isinstance(item.get('id'),int):continue
            hits.append({'project_id':'cf:'+str(item['id']),'title':item.get('name',''),
                         'description':item.get('summary',''),'icon_url':(item.get('logo') or {}).get('thumbnailUrl','')})
        return {'hits':hits,'total_hits':int((payload.get('pagination') or {}).get('totalCount',len(hits)))}

    def normalized_versions(self,mod_id):
        result=[]
        files=[]
        for index in range(0,500,50):
            payload=self._get(f'/mods/{int(mod_id)}/files',{'index':index,'pageSize':50})
            page=payload.get('data') or []
            if not isinstance(page,list):raise CurseForgeError('文件列表格式无效')
            files.extend(page)
            total=(payload.get('pagination') or {}).get('totalCount')
            if len(page)<50 or not isinstance(total,int) or index+len(page)>=total:break
        for file in files:
            if not isinstance(file,dict):continue
            versions=file.get('gameVersions') or [];known={'fabric','forge','neoforge','quilt','liteloader'}
            loaders=[str(v).lower() for v in versions if str(v).lower() in known]
            sha1=next((h.get('value','') for h in file.get('hashes') or [] if h.get('algo')==1),'')
            url=file.get('downloadUrl') or ''
            usable=isinstance(url,str) and url.startswith('https://') and isinstance(sha1,str) and bool(re.fullmatch(r'[0-9a-fA-F]{40}',sha1))
            result.append({'id':str(file.get('id')),'project_id':'cf:'+str(mod_id),'name':file.get('displayName',''),
                'version_number':file.get('displayName',''),'version_type':{1:'release',2:'beta',3:'alpha'}.get(file.get('releaseType'),'release'),
                'date_published':file.get('fileDate',''),'game_versions':[v for v in versions if str(v).lower() not in known],
                'loaders':loaders,'cf_dependencies':[d for d in file.get('dependencies') or [] if d.get('relationType')==3],
                'files':[{'filename':file.get('fileName',''),'url':url,'size':file.get('fileLength'),'hashes':{'sha1':sha1},'primary':True}] if usable else []})
        return result

    def mod(self, mod_id: int) -> dict:
        return self._get(f"/mods/{int(mod_id)}")["data"]

    def file(self, mod_id: int, file_id: int) -> dict:
        return self._get(f"/mods/{int(mod_id)}/files/{int(file_id)}")["data"]

    def files(self, mod_id: int, game_version: str = "",
              loader: str = "", index: int = 0, page_size: int = 50) -> list[dict]:
        params = {"index": index, "pageSize": page_size}
        if game_version:
            params["gameVersion"] = game_version
        if loader:
            params["modLoaderType"] = loader
        return self._get(f"/mods/{int(mod_id)}/files", params).get("data") or []

    # ------------------------------------------------------------ 下载

    def file_url(self, file: dict) -> str:
        """取文件的下载地址；没有 downloadUrl 时按 CDN 规则拼接。"""
        url = str(file.get("downloadUrl") or "").strip()
        if url:
            return url
        file_id = int(file.get("id") or 0)
        name = str(file.get("fileName") or "")
        if not file_id or not name:
            raise CurseForgeError("文件缺少 id / fileName，无法拼接下载地址")
        return cdn_url(file_id, name)

    def target_dir(self, file: dict) -> str:
        """根据 classId 猜测安装目录。"""
        class_id = int(file.get("classId") or 0)
        if class_id in CLASS_DIRS:
            return CLASS_DIRS[class_id]
        name = str(file.get("fileName") or "").lower()
        if name.endswith((".zip",)) and "shader" in name:
            return "shaderpacks"
        return "mods"


def resolve_required_versions(downloader,api_key,root,game,loader,job=None):
    """Resolve required CurseForge dependencies before touching the mod folder."""
    from .catalog import pick_version
    client=CurseForgeClient(downloader,api_key);chosen={};visiting=set()
    def visit(version):
        if job and job.cancel.is_set():raise DownloadCancelled('模组安装已取消')
        project=version.get('project_id','')
        if project in chosen:
            if chosen[project]['id']!=version['id']:raise CurseForgeError('依赖存在版本冲突：'+project)
            return
        if project in visiting:return
        if len(chosen)+len(visiting)>=128:raise CurseForgeError('依赖数量超过安全上限')
        if not version.get('files'):raise CurseForgeError('作者未提供可用的第三方下载地址或 SHA-1')
        visiting.add(project)
        for dependency in version.get('cf_dependencies') or []:
            ident=dependency.get('modId')
            if type(ident) is not int or ident<=0:raise CurseForgeError('前置依赖信息无效')
            candidates=client.normalized_versions(ident)
            candidates=[v for v in candidates if v.get('files') and v.get('version_type')=='release']
            selected=pick_version(candidates,game,loader)
            if not selected:raise CurseForgeError('没有适用的必需前置版本：'+str(ident))
            visit(selected)
        visiting.remove(project);chosen[project]=version
    visit(root)
    return list(chosen.values())
