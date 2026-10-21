# -*- coding: utf-8 -*-
from launcher.launch import substitute


def test_basic_substitution():
    assert substitute("${auth_player_name} here", {"auth_player_name": "Steve"}) == "Steve here"


def test_missing_kept():
    assert substitute("${nope} x", {"auth_player_name": "S"}) == "${nope} x"


def test_multiple():
    out = substitute("${a}${b}", {"a": "1", "b": "2"})
    assert out == "12"
