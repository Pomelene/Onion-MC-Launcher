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
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{base}: {exc}")
        hint = "" if self.api_key else "（可在设置里填写 CurseForge API Key）"
        raise CurseForgeError("CurseForge 接口不可用" + hint + "：" + "；".join(errors))

    # ------------------------------------------------------------ 查询

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