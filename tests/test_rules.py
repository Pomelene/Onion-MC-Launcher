# -*- coding: utf-8 -*-
from launcher.rules import evaluate_rules, os_name


def test_no_rules_allows():
    assert evaluate_rules(None) is True
    assert evaluate_rules([]) is True


def test_allow_all():
    assert evaluate_rules([{"action": "allow"}]) is True


def test_no_match_disallows():
    # 存在 rules 但都不命中 → 默认不允许（HMCL 语义）
    rules = [{"action": "allow", "os": {"name": "__never__"}}]
    assert evaluate_rules(rules) is False


def test_last_match_wins():
    rules = [{"action": "allow"}, {"action": "disallow", "os": {"name": os_name()}}]
    assert evaluate_rules(rules) is False
    rules2 = [{"action": "disallow"}, {"action": "allow", "os": {"name": os_name()}}]
    assert evaluate_rules(rules2) is True


def test_os_restriction():
    assert evaluate_rules([{"action": "allow", "os": {"name": os_name()}}]) is True
    assert evaluate_rules([{"action": "allow", "os": {"name": "linux" if os_name() != "linux" else "osx"}}]) is False


def test_features_match():
    rules = [{"action": "allow", "features": {"is_demo_user": True}}]
    assert evaluate_rules(rules, {"is_demo_user": True}) is True
    assert evaluate_rules(rules, {"is_demo_user": False}) is False
