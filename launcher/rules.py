# -*- coding: utf-8 -*-
"""兼容性规则（rules）求值。

Minecraft 版本 JSON 中 libraries 与 arguments 都可能带 rules，
形如：{"rules": [{"action": "allow", "os": {"name": "windows"}}, ...]}。

语义：按顺序逐条匹配，某条规则命中后，allow/disallow 决定最终结果；
全部未命中则默认允许（allow）。
"""

import platform
import re
import sys
from dataclasses import dataclass
from typing import Any, Optional


def os_name() -> str:
    """返回 Mojang 约定的操作系统名：windows / osx / linux。"""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("darwin"):
        return "osx"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


def os_arch() -> str:
    """返回本机架构（小写），如 amd64 / x86_64。"""
    return platform.machine().lower()


def _arch_matches(rule_arch: str) -> bool:
    """规则 arch 与当前架构是否匹配（x86_64 与 amd64 互通）。"""
    cur = os_arch()
    r = rule_arch.lower()
    if r == cur:
        return True
    if r in ("x86_64", "amd64") and cur in ("x86_64", "amd64"):
        return True
    if r == "x86" and cur in ("x86", "i386", "i686"):
        return True
    return False


@dataclass
class OSRestriction:
    """os 条件：name / arch / version。"""

    name: Optional[str] = None
    arch: Optional[str] = None
    version: Optional[str] = None

    @classmethod
    def from_json(cls, data: Any) -> "OSRestriction":
        if not isinstance(data, dict):
            return cls()
        return cls(name=data.get("name"), arch=data.get("arch"), version=data.get("version"))

    def matches(self) -> bool:
        if self.name is not None and self.name != os_name():
            return False
        if self.arch is not None and not _arch_matches(self.arch):
            return False
        if self.version is not None:
            try:
                if not re.search(self.version, platform.version()):
                    return False
            except re.error:
                return False
        return True


def _features_match(rule_features: Any, actual: dict) -> bool:
    """features 条件匹配：规则里每个键的实际取值必须一致。"""
    if not rule_features:
        return True
    if not isinstance(rule_features, dict):
        return False
    return all(actual.get(k) is v for k, v in rule_features.items())


def evaluate_rules(rules: Any, features: Optional[dict] = None) -> bool:
    """求值一组 rules，返回是否允许。features 形如 {"is_demo_user": bool, ...}。

    规则项可带 os 与 features 两个条件，二者都满足才算命中。
    """
    if not rules:
        return True
    features = features or {}
    # HMCL 语义：存在 rules 时默认不允许，逐条匹配、最后命中者生效
    allowed = False
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        action = rule.get("action", "allow")
        os_cond = OSRestriction.from_json(rule.get("os")).matches()
        feat_cond = _features_match(rule.get("features"), features)
        if os_cond and feat_cond:
            allowed = action == "allow"
    return allowed
