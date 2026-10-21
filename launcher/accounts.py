# -*- coding: utf-8 -*-
"""账号模型与持久化。

账号分两类：离线（offline）与微软正版（microsoft）。
保存在 config/accounts.json，与设置分离，便于单独管理。
"""

import hashlib
import json
import re
import threading
import time
import uuid as uuid_lib
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Optional


_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def validate_username(name: str) -> Optional[str]:
    """校验离线玩家名；合法返回 None，否则返回中文错误信息。"""
    name = (name or "").strip()
    if not _USERNAME_RE.match(name):
        return "玩家名需为 3–16 位字母、数字或下划线"
    return None


def offline_uuid(name: str) -> str:
    """离线账号 UUID：与 Java UUID.nameUUIDFromBytes(("OfflinePlayer:"+name)) 等价（MD5 版本 3）。"""
    digest = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30  # version 3
    digest[8] = (digest[8] & 0x3F) | 0x80  # RFC 4122 variant
    return str(uuid_lib.UUID(bytes=bytes(digest)))


@dataclass
class AccountRecord:
    """一个已保存的账号。"""

    type: str                    # offline | microsoft
    username: str
    uuid: str
    access_token: str = field(default="", repr=False)
    refresh_token: str = field(default="", repr=False)
    expires_at: float = 0.0
    client_id: str = ""          # 微软账号登录时使用的 client_id
    user_type: str = "legacy"    # legacy（离线）| msa（微软）
    authlib_url: str = ""
    client_token: str = field(default="", repr=False)
    xuid: str = ""

    @property
    def label(self) -> str:
        kind = {"microsoft": "正版", "authlib": "外置"}.get(self.type, "离线")
        return f"{self.username}（{kind}）"

    def is_expired(self) -> bool:
        if self.type != "microsoft":
            return False
        return not self.access_token or self.expires_at <= 0 or time.time() >= self.expires_at - 120


class AccountStore:
    """账号列表的读写与当前账号选择。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.accounts: list[AccountRecord] = []
        self.current_uuid: str = ""
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.current_uuid = data.get("current", "")
        self.accounts = [AccountRecord(**item) for item in data.get("accounts", [])
                         if isinstance(item, dict) and item.get("type") and item.get("username")]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"current": self.current_uuid, "accounts": [asdict(a) for a in self.accounts]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ---------- 操作 ----------

    def add(self, account: AccountRecord) -> None:
        with self._lock:
            self.accounts = [a for a in self.accounts
                             if not (a.type == account.type and a.uuid == account.uuid)]
            self.accounts.append(account)
            if not self.current_uuid:
                self.current_uuid = account.uuid
            self.save()

    def remove(self, uuid: str) -> None:
        with self._lock:
            self.accounts = [a for a in self.accounts if a.uuid != uuid]
            if self.current_uuid == uuid:
                self.current_uuid = self.accounts[0].uuid if self.accounts else ""
            self.save()

    def set_current(self, uuid: str) -> None:
        with self._lock:
            if any(a.uuid == uuid for a in self.accounts):
                self.current_uuid = uuid
                self.save()

    def current(self) -> Optional[AccountRecord]:
        for a in self.accounts:
            if a.uuid == self.current_uuid:
                return a
        return self.accounts[0] if self.accounts else None

    def get(self, uuid: str) -> Optional[AccountRecord]:
        for a in self.accounts:
            if a.uuid == uuid:
                return a
        return None

    def update(self, account: AccountRecord) -> None:
        with self._lock:
            self.accounts = [a for a in self.accounts if a.uuid != account.uuid]
            self.accounts.append(account)
            self.save()

    def refresh(self, account: AccountRecord) -> AccountRecord:
        """微软账号过期时用 refresh_token 续期；其它类型原样返回。"""
        if account.type != "microsoft":
            return account
        if not account.refresh_token or not account.client_id:
            raise RuntimeError("账号缺少续期信息，请重新登录")
        from .auth.microsoft import refresh_minecraft
        data = refresh_minecraft(account.client_id, account.refresh_token)
        if data.get("uuid") and uuid_lib.UUID(data["uuid"]) != uuid_lib.UUID(account.uuid):
            raise RuntimeError("续期返回的玩家档案与已保存账号不一致，请重新登录")
        refreshed = replace(account, access_token=data["access_token"],
                            refresh_token=data.get("refresh_token") or account.refresh_token,
                            expires_at=data["expires_at"],
                            username=data.get("username") or account.username,
                            xuid=data.get("xuid") or account.xuid)
        self.update(refreshed)
        return refreshed

    def ensure_fresh(self, account: Optional[AccountRecord]) -> Optional[AccountRecord]:
        """返回可用的当前账号（微软账号过期则先续期，失败返回 None 并记录）。"""
        if account is None:
            return None
        if account.is_expired():
            try:
                return self.refresh(account)
            except Exception as exc:  # noqa: BLE001
                from .log import get_logger
                get_logger().warning("微软账号续期失败：%s", exc)
                return None
        return account
