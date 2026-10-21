# -*- coding: utf-8 -*-
"""命令行入口：不依赖图形界面即可安装、启动与检查版本。

用法示例：
    python -m launcher.cli list
    python -m launcher.cli install 1.20.4 --source bmclapi
    python -m launcher.cli launch 1.20.4 --user Steve
    python -m launcher.cli verify 1.20.4
"""

import argparse
import sys
from pathlib import Path

from .config import Config
from .java import download_java, pick_java
from .paths import app_root, default_settings_path
from .repository import GameRepository


def _progress_printer():
    state = {"last": -1}

    def on_stage(text: str) -> None:
        state["last"] = -1
        print(f"[阶段] {text}", flush=True)

    def on_progress(done: int, total: int) -> None:
        if total <= 0:
            return
        pct = int(done * 100 / total)
        if pct != state["last"]:
            state["last"] = pct
            print(f"\r  进度 {done}/{total} ({pct}%)", end="", flush=True)
            if done >= total:
                print(flush=True)

    return on_stage, on_progress


def cmd_list(repo: GameRepository) -> int:
    installed = repo.list_installed()
    if not installed:
        print("尚未安装任何版本。")
        return 0
    print("已安装版本：")
    for vid in installed:
        info = repo.version_summary(vid)
        print(f"  {vid:<28} {info['type']:<10} {info['release_time']}")
    return 0


def cmd_install(repo: GameRepository, version: str) -> int:
    on_stage, on_progress = _progress_printer()
    rv = repo.install(version, on_stage=on_stage, on_progress=on_progress)
    print(f"安装完成：{rv.id}（主类 {rv.main_class}）")
    return 0


def cmd_optifine(repo: GameRepository, version: str, edition: str = "",
                 java: str = "", list_only: bool = False) -> int:
    """列出或安装 OptiFine。"""
    from .install.optifine import install, list_editions, pick_edition
    from .java import pick_java

    if list_only:
        items = list_editions(repo.downloader, version)
        if not items:
            print(f"{version} 没有可用的 OptiFine 版本。")
            return 1
        for item in items:
            kind = "预览" if item["preview"] else "稳定"
            print(f"{item['label']:<18} {kind}  {item['filename']:<46} {item['forge']}")
        return 0

    chosen = pick_edition(repo.downloader, version, edition)
    if not chosen:
        print(f"找不到 OptiFine {edition or '稳定版'}（可先 --list 查看）。")
        return 1

    if not java:
        try:
            required = max(8, repo.resolver.resolve(version).java_major or 8)
        except Exception:  # noqa: BLE001
            required = 8
        info = pick_java(required)
        if not info:
            print(f"没有找到 Java {required}+，请用 --java 指定。")
            return 1
        java = str(info.path)
        print(f"使用 Java {info.major}：{java}")

    on_stage, on_progress = _progress_printer()
    try:
        vid = install(repo, version, chosen, java_path=java,
                      on_stage=on_stage, on_progress=on_progress)
    except Exception as exc:  # noqa: BLE001
        print(f"OptiFine 安装失败：{exc}")
        return 1
    print(f"OptiFine 安装完成：{vid}（启动器里可直接选择该版本）")
    return 0


def cmd_verify(repo: GameRepository, version: str, deep: bool = False) -> int:
    problems = repo.verify(version, deep=deep)
    if not problems:
        print(f"{version} 校验通过，文件完整。")
        return 0
    print(f"{version} 存在 {len(problems)} 个问题：")
    for p in problems:
        print("  -", p)
    return 1


def cmd_accounts(repo: GameRepository, action: str, name: str) -> int:
    from .accounts import AccountRecord, AccountStore, offline_uuid, validate_username
    from .paths import default_accounts_path
    store = AccountStore(default_accounts_path())
    if action == "list":
        if not store.accounts:
            print("尚无账号。")
        for a in store.accounts:
            mark = " ← 当前" if a.uuid == store.current_uuid else ""
            print(f"{a.username:<20} {a.type:<10} {a.uuid}{mark}")
        return 0
    if action == "add":
        err = validate_username(name)
        if err:
            print(f"错误：{err}")
            return 1
        uid = offline_uuid(name)
        if any(a.uuid == uid for a in store.accounts):
            print("账号已存在。")
            return 0
        store.add(AccountRecord(type="offline", username=name, uuid=uid, access_token="0"))
        store.set_current(uid)
        print(f"已添加离线账号 {name}（{uid}）")
        return 0
    if action == "switch":
        for a in store.accounts:
            if a.username == name or a.uuid == name:
                store.set_current(a.uuid)
                print(f"已切换当前账号到 {a.username}")
                return 0
        print("未找到该账号。")
        return 1
    return 2


def cmd_java() -> int:
    from .java import find_all_java
    infos = find_all_java()
    if not infos:
        print("未发现可用的 Java。")
        return 1
    for info in infos:
        print(f"Java {info.major:<3} {info.version:<16} {info.path}")
    return 0


def cmd_launch(repo: GameRepository, version: str, user: str, java_opt: str) -> int:
    from .launch import Account, LaunchSettings, launch
    on_stage, on_progress = _progress_printer()
    rv = repo.install(version, on_stage=on_stage, on_progress=on_progress)

    from .java import resolve_java
    java_info = resolve_java(rv.java_major, java_opt, repo.downloader, on_stage, on_progress)
    if java_info is None:
        print("没有可用的 Java，无法启动。")
        return 1
    print(f"使用 Java {java_info.major}：{java_info.path}")

    from .accounts import offline_uuid, validate_username
    if validate_username(user):
        raise ValueError(validate_username(user))
    account = Account(username=user, uuid=offline_uuid(user), access_token="0", user_type="legacy")
    settings = LaunchSettings(java_path=str(java_info.path))
    print("启动游戏……（日志如下）")
    proc = launch(repo, rv, account, settings, str(java_info.path),
                  on_log=lambda line, is_err: print(("ERR " if is_err else "    ") + line, flush=True),
                  on_exit=lambda code: print(f"\n游戏退出，代码 {code}", flush=True))
    try:
        proc.proc.wait()
    except KeyboardInterrupt:
        proc.stop()
    return 0


def cmd_sync(repo, args) -> int:
    """并行同步多源信息并打印状态。"""
    import json
    from .aggregator import InfoHub

    hub = InfoHub(repo.downloader)
    hub.load_cache()
    hub.refresh(keys=args.only or None, force=bool(args.force),
                on_status=lambda status: print(f"  {status.label()}", flush=True))
    if args.json:
        payload = {
            "sources": [
                {"key": s.key, "state": s.state, "count": s.count,
                 "latency_ms": s.latency_ms, "error": s.error,
                 "from_cache": s.from_cache} for s in hub.status_list()
            ],
            "game_versions": len(hub.game_versions()),
            "fabric_loaders": len(hub.loaders("fabric")),
            "forge_versions": len(hub.loaders("forge")),
            "neoforge_versions": len(hub.loaders("neoforge")),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print()
        for status in hub.status_list():
            print(f"{status.state:8} {status.label()}")
        print()
        print(f"游戏版本：{len(hub.game_versions())} 个")
        print(f"Fabric 加载器：{len(hub.loaders('fabric'))} 个")
        for key in ("forge", "neoforge", "quilt"):
            print(f"{key} 版本：{len(hub.loaders(key))} 个")
    return 0 if all(s.state == "ok" for s in hub.status_list()) else 1


def cmd_trial(config, args) -> int:
    """试运行参考实例矩阵，输出报告；参考目录只读。"""
    import shutil
    from .trial import render_report, run_trial

    ref = Path(args.ref)
    if not (ref / "versions").is_dir():
        print(f"参考目录无效（缺少 versions）：{ref}")
        return 2
    sandbox_root = Path(args.sandbox) if args.sandbox else None
    if args.fresh and sandbox_root is not None:
        shutil.rmtree(sandbox_root, ignore_errors=True)
    run = run_trial(
        config, ref,
        instance_ids=args.instance or None,
        timeout=float(args.timeout),
        keep=bool(args.keep),
        sandbox_root=sandbox_root,
        shots_dir=Path(args.shots) if args.shots else None,
        on_event=lambda text: print(text, flush=True),
    )
    report = render_report(run)
    out = Path(args.report) if args.report else (app_root() / "docs" / "trial-report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print()
    print(report)
    print()
    print(f"报告已写入 {out}")
    clean = not run.diff.get("added") and not run.diff.get("removed") and not run.diff.get("changed")
    return 0 if (run.passed == run.runnable and run.runnable > 0 and clean) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="craftbridge", description="Onion Minecraft Launcher 命令行工具")
    parser.add_argument("--source", help="下载源：mojang / bmclapi")
    parser.add_argument("--game-dir", help="游戏目录")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="列出已安装版本")
    p_install = sub.add_parser("install", help="安装指定版本")
    p_install.add_argument("version")
    p_verify = sub.add_parser("verify", help="校验版本完整性")
    p_verify.add_argument("version")
    p_verify.add_argument("--deep", action="store_true", help="额外做 SHA-1 校验")
    sub.add_parser("loaders", help="列出可下载的 Java 运行时")
    p_export = sub.add_parser("export", help="把版本导出为 .mrpack")
    p_export.add_argument("version")
    p_export.add_argument("out", nargs="?", default="")
    p_accounts = sub.add_parser("accounts", help="账号管理（list / add / switch）")
    p_accounts.add_argument("action", choices=["list", "add", "switch"])
    p_accounts.add_argument("name", nargs="?", default="")
    sub.add_parser("doctor", help="环境诊断")
    p_import = sub.add_parser("import", help="导入整合包（.mrpack / CurseForge zip）")
    p_import.add_argument("file")
    p_launch = sub.add_parser("launch", help="安装并启动版本")
    p_launch.add_argument("version")
    p_launch.add_argument("--user", default="Steve")
    p_launch.add_argument("--java", default="")
    sub.add_parser("java", help="列出发现的 Java")
    p_trial = sub.add_parser("trial", help="试运行参考目录中的实例（只读参考目录）")
    p_trial.add_argument("--ref", default=r"F:\.minecraft", help="参考游戏目录")
    p_trial.add_argument("--instance", action="append", default=[], help="只跑指定实例（可多次）")
    p_trial.add_argument("--timeout", type=float, default=180.0, help="等待开始界面的秒数")
    p_trial.add_argument("--keep", action="store_true", help="结束后保留沙箱")
    p_trial.add_argument("--fresh", action="store_true", help="运行前清空沙箱")
    p_trial.add_argument("--sandbox", default="", help="沙箱根目录")
    p_trial.add_argument("--shots", default="", help="截图输出目录")
    p_trial.add_argument("--report", default="", help="报告输出路径")
    p_sync = sub.add_parser("sync", help="并行同步多源信息（版本/加载器/Java）")
    p_sync.add_argument("--json", action="store_true", help="以 JSON 输出")
    p_sync.add_argument("--force", action="store_true", help="忽略缓存强制刷新")
    p_sync.add_argument("--only", action="append", default=[], help="只同步指定源")
    p_bench = sub.add_parser("bench", help="运行本地性能基线")
    p_bench.add_argument("--rounds", type=int, default=3, help="每项重复次数（取最小值）")
    p_optifine = sub.add_parser("optifine", help="列出或安装 OptiFine")
    p_optifine.add_argument("version", help="原版版本号，如 1.20.4")
    p_optifine.add_argument("--edition", default="", help="如 HD_U_I7，默认最新稳定版")
    p_optifine.add_argument("--java", default="", help="运行安装器的 Java 路径")
    p_optifine.add_argument("--list", action="store_true", help="只列出可用版本")
    args = parser.parse_args(argv)

    config = Config(default_settings_path())
    if args.source:
        config.set("download_source", args.source)
    if args.game_dir:
        config.set("game_dir", args.game_dir)
    repo = GameRepository(config)

    if args.cmd == "list":
        return cmd_list(repo)
    if args.cmd == "install":
        return cmd_install(repo, args.version)
    if args.cmd == "verify":
        return cmd_verify(repo, args.version, args.deep)
    if args.cmd == "loaders":
        from .java import list_downloadable
        for item in list_downloadable(repo.downloader):
            print(f"Java {item['major']:<3} {item['name']:<24} {item['released']}")
        return 0
    if args.cmd == "export":
        from .modpack import export_mrpack
        out = Path(args.out) if args.out else Path(f"{args.version}.mrpack")
        export_mrpack(repo, args.version, out)
        print(f"已导出：{out}")
        return 0
    if args.cmd == "accounts":
        return cmd_accounts(repo, args.action, args.name)
    if args.cmd == "doctor":
        from .doctor import run_diagnosis, format_diagnosis
        print(format_diagnosis(run_diagnosis(repo.game_dir, repo.downloader)))
        return 0
    if args.cmd == "java":
        return cmd_java()
    if args.cmd == "import":
        from .modpack import import_modpack
        on_stage, on_progress = _progress_printer()
        vid = import_modpack(repo, Path(args.file), on_stage, on_progress)
        print(f"整合包导入完成：{vid}")
        return 0
    if args.cmd == "launch":
        return cmd_launch(repo, args.version, args.user, args.java)
    if args.cmd == "trial":
        return cmd_trial(config, args)
    if args.cmd == "sync":
        return cmd_sync(repo, args)
    if args.cmd == "bench":
        from .perf import format_bench, run_bench
        print(format_bench(run_bench(repo, rounds=max(1, args.rounds))))
        return 0
    if args.cmd == "optifine":
        return cmd_optifine(repo, args.version, args.edition, args.java, args.list)
    return 2


if __name__ == "__main__":
    sys.exit(main())
