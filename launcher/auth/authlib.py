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
from ..network import secure_open,validate_url
from ..paths import LAUNCHER_VERSION

INJECTOR_URL='https://github.com/yushijinhun/authlib-injector/releases/download/v1.2.8/authlib-injector-1.2.8.jar'
INJECTOR_SHA256='9c7f4343e6c82034958ffb48c14a2cb0c85928be7283103ce17da00c6d5a7b10'
INJECTOR_SIZE=349681


def _post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": f"Onion Minecraft Launcher/{LAUNCHER_VERSION}",
    })
    try:
        with secure_open(req, timeout=30) as resp:
            content=resp.read(1024**2+1)
            if len(content)>1024**2:raise DownloadError('认证响应过大')
            return json.loads(content.decode("utf-8"))
    except urllib.error.HTTPError as e:
        status=e.code;e.close()
        raise DownloadError(f"外置认证失败（HTTP {status}），请检查账号或联系验证服务器维护者") from None
    except urllib.error.URLError as e:
        raise DownloadError('无法连接验证服务器，请检查网络后重试') from None
    except (ValueError,UnicodeError,OSError):
        raise DownloadError('验证服务器地址或响应无效') from None


def ensure_injector(downloader, dest: Path) -> Path:
    """Use a pinned official release and validate its SHA-256, including cache."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    downloader.download_one(DownloadJob(INJECTOR_URL,dest,sha256=INJECTOR_SHA256,
                                      size=INJECTOR_SIZE,name='authlib-injector-1.2.8.jar'))
    return dest


def authenticate(server_url: str, username: str, password: str) -> dict:
    """用邮箱+密码登录外置验证服务器。

    返回 {username, uuid, access_token, authlib_url, user_type}。
    """
    validate_url((server_url or '').strip(),https_only=True)
    url = server_url.strip().rstrip("/") + "/authserver/authenticate"
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
