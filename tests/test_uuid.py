# -*- coding: utf-8 -*-
from launcher.accounts import offline_uuid, validate_username


def test_offline_uuid_known():
    # 与 Java UUID.nameUUIDFromBytes("OfflinePlayer:Steve") 等价
    assert offline_uuid("Steve") == "5627dd98-e6be-3c21-b8a8-e92344183641"
    assert offline_uuid("Notch") == "b50ad385-829d-3141-a216-7e7d7539ba7f"


def test_validate_username():
    assert validate_username("Steve") is None
    assert validate_username(" abc_123 ") is None
    assert validate_username("a") is not None
    assert validate_username("非法中文名!") is not None
    assert validate_username("this_name_is_way_too_long") is not None
