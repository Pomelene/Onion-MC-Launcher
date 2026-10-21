# -*- coding: utf-8 -*-
"""下载源（镜像）定义与 URL 改写。

官方 Mojang 服务器在部分网络环境下较慢，主流启动器都提供镜像；
本模块把"原始 URL"统一改写为目标下载源的地址，其余模块只关心原始 URL。
"""

MOJANG = "mojang"
BMCLAPI = "bmclapi"
MCBBS = "mcbbbs"

#: 可供界面选择的所有下载源：value -> 显示名
ALL_SOURCES = {
    MOJANG: "Mojang 官方",
    BMCLAPI: "BMCLAPI（推荐）",
    MCBBS: "MCBBS 镜像",
}

MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest.json"
BMCLAPI_MANIFEST = "https://bmclapi2.bangbang93.com/mc/game/version_manifest.json"
MCBBS_MANIFEST = "https://download.mcbbs.net/mc/game/version_manifest.json"


class DownloadSource:
    """下载源：提供版本清单地址、版本 JSON / 客户端 jar 地址与 URL 改写。"""

    def __init__(self, name: str = MOJANG):
        self.name = name if name in ALL_SOURCES else MOJANG

    @property
    def display_name(self) -> str:
        return ALL_SOURCES.get(self.name, self.name)

    # ---------- 版本清单 / 版本 JSON / 客户端 jar ----------

    def version_manifest_url(self) -> str:
        if self.name == BMCLAPI:
            return BMCLAPI_MANIFEST
        if self.name == MCBBS:
            return MCBBS_MANIFEST
        return MOJANG_MANIFEST

    def version_json_url(self, version_id: str) -> str:
        """按版本 id 直接获取版本 JSON（用于清单里找不到 URL 时兜底）。"""
        if self.name == BMCLAPI:
            return f"https://bmclapi2.bangbang93.com/mc/game/version/{version_id}/json"
        if self.name == MCBBS:
            return f"https://download.mcbbs.net/mc/game/version/{version_id}/json"
        return f"https://launchermeta.mojang.com/mc/game/version/{version_id}/json"

    def client_jar_url(self, version_id: str) -> str:
        """镜像的客户端 jar 地址；官方源应优先使用版本 JSON 里的 downloads.client.url。"""
        if self.name == BMCLAPI:
            return f"https://bmclapi2.bangbang93.com/version/{version_id}/client"
        if self.name == MCBBS:
            return f"https://download.mcbbs.net/version/{version_id}/client"
        return f"https://launcher.mojang.com/v1/objects/{version_id}/client.jar"

    def server_jar_url(self, version_id: str) -> str:
        if self.name == BMCLAPI:
            return f"https://bmclapi2.bangbang93.com/version/{version_id}/server"
        if self.name == MCBBS:
            return f"https://download.mcbbs.net/version/{version_id}/server"
        return f"https://launcher.mojang.com/v1/objects/{version_id}/server.jar"

    # ---------- 通用 URL 改写 ----------

    def remap(self, url: str) -> str:
        """把官方 URL 改写为当前下载源的等价地址；无法改写时原样返回。"""
        if not url:
            return url
        if self.name == MOJANG:
            return url
        # 镜像不提供 /v1/objects（日志配置、旧版客户端 jar）与 /v1/packages，
        # 这些地址必须保持官方，否则会 404。
        if "/v1/objects/" in url or "/v1/packages/" in url:
            return url
        base = self._mirror_base()
        if not base:
            return url
        for src, dst in self._RULES.get(self.name, []):
            if url.startswith(src):
                return dst + url[len(src):]
        return url

    def _mirror_base(self) -> str:
        if self.name == BMCLAPI:
            return "https://bmclapi2.bangbang93.com/"
        if self.name == MCBBS:
            return "https://download.mcbbs.net/"
        return ""

    #: (官方前缀, 镜像前缀) 替换规则
    _RULES = {
        BMCLAPI: [
            ("https://launchermeta.mojang.com/mc/game/version_manifest_v2.json",
             "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json"),
            ("https://launchermeta.mojang.com", "https://bmclapi2.bangbang93.com"),
            ("https://piston-meta.mojang.com", "https://bmclapi2.bangbang93.com"),
            ("https://launcher.mojang.com", "https://bmclapi2.bangbang93.com"),
            ("https://libraries.minecraft.net", "https://bmclapi2.bangbang93.com/maven"),
            ("https://resources.download.minecraft.net", "https://bmclapi2.bangbang93.com/assets"),
            ("https://meta.fabricmc.net", "https://bmclapi2.bangbang93.com/fabric-meta"),
            ("https://meta.quiltmc.org", "https://bmclapi2.bangbang93.com/quilt-meta"),
            ("https://maven.fabricmc.net", "https://bmclapi2.bangbang93.com/maven"),
            ("https://maven.minecraftforge.net", "https://bmclapi2.bangbang93.com/maven"),
            ("https://maven.neoforged.net/releases", "https://bmclapi2.bangbang93.com/maven"),
        ],
        MCBBS: [
            ("https://launchermeta.mojang.com/mc/game/version_manifest_v2.json",
             "https://download.mcbbs.net/mc/game/version_manifest_v2.json"),
            ("https://launchermeta.mojang.com", "https://download.mcbbs.net"),
            ("https://piston-meta.mojang.com", "https://download.mcbbs.net"),
            ("https://launcher.mojang.com", "https://download.mcbbs.net"),
            ("https://libraries.minecraft.net", "https://download.mcbbs.net/maven"),
            ("https://resources.download.minecraft.net", "https://download.mcbbs.net/assets"),
            ("https://meta.fabricmc.net", "https://download.mcbbs.net/fabric-meta"),
            ("https://meta.quiltmc.org", "https://download.mcbbs.net/quilt-meta"),
            ("https://maven.fabricmc.net", "https://download.mcbbs.net/maven"),
        ],
    }


def make_source(name: str) -> DownloadSource:
    return DownloadSource(name)
