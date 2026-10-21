# -*- coding: utf-8 -*-
"""外置登录（authlib-injector / Yggdrasil API）。

下载官方 authlib-injector，对自定义验证服务器的 /authserver/authenticate
做邮箱+密码登录；启动时通过 -javaagent 注入。
"""

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from ..download import DownloadError, DownloadJob

AUTHLIB_API = "https://api.github.com/repos/yushijinhun/authlib-injector/releases/latest"
AUTHLIB_FALLBACK = "https://github.com/yushijinhun/authlib-injector/releases/latest/download/authlib-injector.jar"


def _post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "Onion Minecraft Launcher/0.2.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise DownloadError(f"登录失败 ({e.code})：{detail[:200]}") from e
    except urllib.error.URLError as e:
        raise DownloadError(f"网络错误：{e.reason}") from e


def ensure_injector(downloader, dest: Path) -> Path:
    """确保 authlib-injector.jar 存在（优先取 GitHub 最新 release，失败回退直链）。"""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = AUTHLIB_FALLBACK
    try:
        data = downloader.fetch_json(AUTHLIB_API)
        assets = data.get("assets") or []
        jar = next((x for x in assets if (x.get("name") or "").endswith(".jar")), None)
        if jar and jar.get("browser_download_url"):
            url = jar["browser_download_url"]
    except Exception:  # noqa: BLE001
        pass
    downloader.download_one(DownloadJob(url, dest, name="authlib-injector.jar"))
    return dest


def authenticate(server_url: str, username: str, password: str) -> dict:
    """用邮箱+密码登录外置验证服务器。

    返回 {username, uuid, access_token, authlib_url, user_type}。
    """
    url = (server_url or "").strip().rstrip("/") + "/authserver/authenticate"
    client_token = uuid.uuid4().hex
    payload = {
        "agent": {"name": "Minecraft", "version": 1},
        "username": username,
        "password": password,
        "clientToken": client_token,
        "requestUser": True,
    }
    resp = _post_json(url, payload)
    profile = resp.get("selectedProfile") or (resp.get("availableProfiles") or [{}])[0] or {}
    if not profile.get("id") or not profile.get("name") or not resp.get("accessToken"):
        raise DownloadError("登录响应没有可用的角色，请先在验证服务器创建角色")
    return {
        "username": profile.get("name", username),
        "uuid": profile.get("id", ""),
        "access_token": resp.get("accessToken", ""),
        "client_token": client_token,
        "authlib_url": (server_url or "").strip().rstrip("/"),
        "user_type": "mojang",
    }
