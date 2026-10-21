# -*- coding: utf-8 -*-
"""CurseForge 客户端与整合包文件下载的单元测试（不访问网络）。"""

import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.curseforge import CurseForgeClient, cdn_url


class _Downloader:
    def __init__(self):
        self.jobs = []

    def download_many(self, jobs, on_progress=None):
        self.jobs.extend(jobs)
        return list(jobs), []


def test_cdn_url_layout():
    assert cdn_url(5846846, "jei.jar") == "https://edge.forgecdn.net/files/5846/846/jei.jar"
    assert cdn_url(123, "a.jar") == "https://edge.forgecdn.net/files/0/123/a.jar"


def test_file_url_prefers_download_url():
    client = CurseForgeClient(_Downloader())
    assert client.file_url({"id": 1, "fileName": "a.jar",
                            "downloadUrl": "https://example.com/a.jar"}) == "https://example.com/a.jar"
    assert client.file_url({"id": 5846846, "fileName": "jei.jar",
                            "downloadUrl": None}) == cdn_url(5846846, "jei.jar")


def test_target_dir_by_class():
    client = CurseForgeClient(_Downloader())
    assert client.target_dir({"classId": 6, "fileName": "x.jar"}) == "mods"
    assert client.target_dir({"classId": 12, "fileName": "x.zip"}) == "resourcepacks"
    assert client.target_dir({"classId": 6552, "fileName": "x.zip"}) == "shaderpacks"
    assert client.target_dir({"classId": 0, "fileName": "shader.zip"}) == "shaderpacks"
    assert client.target_dir({"classId": 0, "fileName": "x.jar"}) == "mods"


def test_install_curseforge_files():
    from launcher import modpack

    class _FakeClient:
        def __init__(self, downloader, api_key=""):
            self.api_key = api_key

        def file(self, mod_id, file_id):
            if file_id == 404:
                raise RuntimeError("not found")
            return {"id": file_id, "fileName": f"mod-{mod_id}.jar",
                    "classId": 6, "downloadUrl": "", "fileLength": 10,
                    "hashes": {"sha1": "0" * 40}}

        def file_url(self, meta):
            return cdn_url(meta["id"], meta["fileName"])

        def target_dir(self, meta):
            return "mods"

    class _Config:
        def get(self, key, default=None):
            return ""

    class _Repo:
        def __init__(self):
            self.downloader = _Downloader()
            self.config = _Config()

    with tempfile.TemporaryDirectory() as tmp, \
         mock.patch("launcher.curseforge.CurseForgeClient", _FakeClient):
        repo = _Repo()
        entries = [{"projectID": 1, "fileID": 2, "required": True},
                   {"projectID": 3, "fileID": 4, "required": False}]
        count = modpack._install_curseforge_files(repo, Path(tmp), entries)
    assert count == 2
    assert len(repo.downloader.jobs) == 2
    targets = sorted(job.path.name for job in repo.downloader.jobs)
    assert targets == ["mod-1.jar", "mod-3.jar"]


def test_install_curseforge_required_failure():
    from launcher import modpack

    class _FakeClient:
        def __init__(self, downloader, api_key=""):
            pass

        def file(self, mod_id, file_id):
            raise RuntimeError("not found")

    class _Config:
        def get(self, key, default=None):
            return ""

    class _Repo:
        def __init__(self):
            self.downloader = _Downloader()
            self.config = _Config()

    with tempfile.TemporaryDirectory() as tmp, \
         mock.patch("launcher.curseforge.CurseForgeClient", _FakeClient):
        try:
            modpack._install_curseforge_files(
                _Repo(), Path(tmp), [{"projectID": 1, "fileID": 404, "required": True}])
        except Exception as exc:
            assert "CurseForge" in str(exc)
        else:
            raise AssertionError("必需文件缺失时应当报错")
