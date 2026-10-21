# -*- coding: utf-8 -*-
"""真实网络压测：清单/镜像/Modrinth/深度校验/命令行构建/导出导入/实例锁。

用法：python -m tests.stress
仅在本地工作区内操作，不触碰 F:\\.minecraft。
"""

import json
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from launcher.accounts import offline_uuid
from launcher.config import Config
from launcher.download import DownloadError
from launcher.java import probe_java, runtime_dir
from launcher.launch import Account, LaunchSettings, build_classpath, build_command
from launcher.modpack import export_mrpack, import_modpack, read_modpack_info
from launcher.paths import default_settings_path
from launcher.repository import GameRepository
from launcher.sources import make_source

results = []


def check(name, fn):
    try:
        t0 = time.time()
        fn()
        results.append((name, True, f"{time.time()-t0:.2f}s", ""))
        print(f"PASS {name} ({time.time()-t0:.2f}s)")
    except Exception as e:  # noqa: BLE001
        results.append((name, False, "", str(e)))
        print(f"FAIL {name}: {e}")


def main():
    cfg = Config(default_settings_path())
    repo = GameRepository(cfg)
    print(f"游戏目录：{repo.game_dir}")
    print(f"下载源：{repo.source.name}")
    print()

    # 1) 环境诊断
    def diag():
        from launcher.doctor import run_diagnosis
        d = run_diagnosis(repo.game_dir, repo.downloader)
        assert d["game_dir_writable"], "游戏目录不可写"
        assert d["java"], "未发现任何 Java"
    check("环境诊断", diag)

    # 2) 版本清单（官方 + BMCLAPI）
    def manifests():
        m = repo.fetch_manifest(force=True)
        assert m.find("1.20.4") is not None
        bm = GameRepository(cfg) if False else None
        src = make_source("bmclapi")
        from launcher.version import VersionManifest
        bm = VersionManifest.fetch(repo.downloader, src.version_manifest_url())
        assert bm.find("1.20.4") is not None
    check("版本清单（Mojang+BMCLAPI）", manifests)

    # 3) Modrinth 搜索
    def modrinth():
        from launcher.catalog import search
        data = search(repo.downloader, "mod", "sodium", "", "", limit=5)
        hits = data.get("hits") or []
        assert hits, "搜索无结果"
        assert data.get("total_hits", 0) > 0
    check("Modrinth 搜索", modrinth)

    # 4) 深度校验已安装版本
    def deep_verify_all():
        bad = []
        for vid in repo.list_installed():
            probs = repo.verify(vid, deep=True)
            if probs:
                bad.append((vid, probs))
        assert not bad, f"损坏版本: {bad}"
    check("深度校验全部已安装版本", deep_verify_all)

    # 5) 命令行构建（干跑，不真正启动）
    def dry_run_command():
        account = Account(username="Steve", uuid=offline_uuid("Steve"),
                          access_token="0", user_type="legacy")
        java = probe_java(runtime_dir("java-runtime-beta") / "bin" / "java.exe")
        if java is None:
            return  # 无运行时则跳过
        for vid in ("1.20.4", "1.20.4-forge-49.2.13", "fabric-loader-0.19.5-1.20.4"):
            rv = repo.resolver.resolve(vid)
            settings = LaunchSettings(java_path=java.executable)
            cp = build_classpath(repo, rv)
            assert cp, f"{vid} classpath 为空"
            cmd = build_command(repo, rv, account, settings, java.executable)
            assert any("-cp" == c for c in cmd) or any(c.startswith("-cp") for c in cmd), "缺少 -cp"
            main = rv.main_class
            assert main and main in cmd, f"{vid} 缺少主类"
    check("启动命令行干跑（原版/Forge/Fabric）", dry_run_command)

    # 6) 导出 + 导入往返（真实网络，但依赖已缓存）
    def export_import_roundtrip():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "roundtrip.mrpack"
            export_mrpack(repo, "fabric-loader-0.19.5-1.20.4", out, "StressRoundtrip")
            info = read_modpack_info(out)
            assert info.kind == "mrpack" and info.game_version == "1.20.4"
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
            assert "modrinth.index.json" in names
            assert any(n.startswith("overrides/mods/") for n in names), "导出缺少 overrides/mods"
            # 构造一个纯原版 + overrides 的极简包，验证真实导入
            mini = Path(d) / "mini.mrpack"
            with zipfile.ZipFile(mini, "w") as zf:
                zf.writestr("modrinth.index.json", json.dumps({
                    "formatVersion": 1, "game": "minecraft", "versionId": "1.0",
                    "name": "StressMini", "files": [],
                    "dependencies": {"minecraft": "1.20.4"}}))
                zf.writestr("overrides/options.txt", "fov:1.0")
            vid = import_modpack(repo, mini)
            assert (repo.version_dir(vid) / "options.txt").exists(), "覆盖文件未解压"
            repo.delete_version(vid)
    check("导出 + 导入往返", export_import_roundtrip)

    # 7) 实例锁
    def instance_lock():
        from launcher.launch import InstanceLock
        import threading
        p = repo.version_dir("1.20.4") / ".lock_test"
        lock = InstanceLock(p)
        assert lock.acquire() is True
        assert InstanceLock(p).acquire() is False, "重复获取应失败"
        lock.release()
        assert InstanceLock(p).acquire() is True
        lock.release()
    check("实例锁", instance_lock)

    # 汇总
    passed = sum(1 for _, ok, _, _ in results if ok)
    total = len(results)
    print(f"\n=== 压测结果：{passed}/{total} 通过 ===")
    lines_out = [
        "# CraftBridge 真实网络压测报告",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 通过：{passed} / {total}",
        "",
        "| 项目 | 结果 | 耗时 | 备注 |",
        "| --- | --- | --- | --- |",
    ]
    for name, ok, dur, err in results:
        lines_out.append(f"| {name} | {'√' if ok else '×'} | {dur} | {err} |")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "stress-report.md").write_text("\n".join(lines_out), encoding="utf-8")
    print("报告已写入 docs/stress-report.md")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
