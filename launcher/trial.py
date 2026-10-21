# -*- coding: utf-8 -*-
"""参考实例试运行：沙箱启动 + 进入开始界面判定 + 只读证明。

判定证据链（全部满足才算成功）：
1. 进程仍存活；
2. 按进程号找到标题含 Minecraft 的可见窗口；
3. 日志尾部没有未捕获异常栈；
4. 沙箱中没有产生新的崩溃报告；
5. 窗口截图不是纯黑/纯白。

模组冲突导致的崩溃按约定不计入启动器缺陷，但仍会记录日志尾部。
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .accounts import offline_uuid
from .foreign import (InstanceInfo, PreflightReport, detect_instances,
                      diff_fingerprints, fingerprint, prepare_sandbox, preflight)
from .java import resolve_java
from .launch import Account, LaunchSettings, launch
from .paths import app_root
from .repository import GameRepository
from .windowwatch import capture_window, kill_tree, screenshot_stats, wait_for_game_window

#: 真正致命的日志片段（启动器/虚拟机层面的失败）
FATAL_MARKERS = (
    "Exception in thread",
    "Uncaught exception",
    "A fatal error has been detected",
    "OutOfMemoryError",
    "Could not find or load main class",
    "Error: Could not find or load main class",
    "Failed to start the game",
    "Unable to access jarfile",
)
#: 模组自身的噪声（按约定不计入启动器缺陷）
MOD_NOISE = (
    "Error loading class:",
    "ClassNotFoundException",
    "Mixin apply failed",
    "Duplicate mods",
    "Missing or unsupported mandatory",
    "Mod resolution",
)


@dataclass
class TrialResult:
    """单个实例的试运行结果。"""

    id: str
    ok: bool = False
    note: str = ""
    seconds: float = 0.0
    window_title: str = ""
    window_seconds: float = 0.0
    screenshot: str = ""
    shot: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    crash: str = ""
    skipped: bool = False
    tail: list[str] = field(default_factory=list)
    preflight: Optional[PreflightReport] = None


@dataclass
class TrialRun:
    """一次完整矩阵运行。"""

    results: list[TrialResult] = field(default_factory=list)
    reference_root: str = ""
    diff: dict = field(default_factory=dict)
    seconds: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def runnable(self) -> int:
        return sum(1 for r in self.results if not r.skipped)


def _log_errors(lines: list[str], limit: int = 8) -> list[str]:
    """只挑出会导致启动失败的错误行；模组自身的类加载噪声被忽略。"""
    hits: list[str] = []
    for line in lines:
        if any(noise in line for noise in MOD_NOISE):
            continue
        if any(marker in line for marker in FATAL_MARKERS):
            hits.append(line.strip()[:300])
            if len(hits) >= limit:
                break
    return hits


def run_trial(cfg, reference_root: Path, instance_ids: Optional[list[str]] = None,
              timeout: float = 180.0, keep: bool = False,
              sandbox_root: Optional[Path] = None,
              shots_dir: Optional[Path] = None,
              on_event: Optional[Callable[[str], None]] = None) -> TrialRun:
    """对参考目录中的实例逐个试运行，返回结果与只读指纹比对。"""
    def emit(text: str) -> None:
        if on_event:
            on_event(text)

    ref_root = Path(reference_root)
    versions_root = ref_root / "versions"
    sandbox_root = Path(sandbox_root or (app_root() / "sandbox"))
    # Legacy read-only trials must never change the user's active management settings.
    from .config import Config
    trial_cfg = Config(sandbox_root / "trial-settings.json")
    trial_cfg.data = dict(cfg.data)
    trial_cfg.update({"game_dir": str(sandbox_root / "repository"), "foreign_mode": True,
                      "reference_roots": [str(ref_root)]})
    cfg = trial_cfg
    repo = GameRepository(cfg)
    shots_dir = Path(shots_dir or (app_root() / "docs" / "screens"))
    shots_dir.mkdir(parents=True, exist_ok=True)

    all_instances = detect_instances(versions_root)
    if instance_ids:
        wanted = {i.lower() for i in instance_ids}
        all_instances = [i for i in all_instances if i.id.lower() in wanted]

    run = TrialRun(reference_root=str(ref_root))
    started = time.time()
    emit(f"参考目录：{ref_root}（{len(all_instances)} 个实例）")
    before = fingerprint(ref_root)

    for inst in all_instances:
        result = TrialResult(id=inst.id)
        run.results.append(result)
        t0 = time.time()
        emit(f"[{inst.id}] 预检")
        report = preflight(repo, ref_root, inst)
        result.preflight = report
        if not report.ok:
            result.note = "; ".join(report.notes) or "预检未通过"
            result.skipped = not inst.runnable
            result.seconds = time.time() - t0
            emit(f"[{inst.id}] 跳过：{result.note}")
            continue

        log_lines: list[str] = []
        proc = None
        try:
            emit(f"[{inst.id}] 导入版本 JSON")
            repo.import_external_version(versions_root, inst.id)
            sandbox = prepare_sandbox(inst, sandbox_root / inst.id,
                                      int(cfg.get("sandbox_budget_mb") or 512))
            emit(f"[{inst.id}] 沙箱就绪（复制 {len(sandbox.copied)} 项，"
                 f"联接 {len(sandbox.linked)} 项）")
            rv = repo.install(inst.id,
                              on_stage=lambda text: emit(f"[{inst.id}] {text}"),
                              on_progress=None)
            required_major = rv.java_major
            if required_major is None:
                from .foreign import detect_mod_java_requirement
                required_major = detect_mod_java_requirement(inst.dir / "mods")
                if required_major:
                    emit(f"[{inst.id}] 模组要求 Java {required_major}，据此解析运行时")
            java = resolve_java(required_major, cfg.get("java_path") or "",
                                repo.downloader,
                                on_stage=lambda text: emit(f"[{inst.id}] {text}"))
            if java is None:
                result.note = f"未找到可用的 Java（需要 {rv.java_major}）"
                continue
            emit(f"[{inst.id}] 使用 Java {java.major}：{java.path}")
            account = Account(username="Trial", uuid=offline_uuid("Trial"))
            settings = LaunchSettings(
                java_path=str(java.path),
                max_memory=int(cfg.get("max_memory") or 4096),
                min_memory=int(cfg.get("min_memory") or 2048),
                width=854, height=480,
                launcher_name=str(cfg.get("launcher_name") or "Onion Minecraft Launcher"),
                game_dir_override=str(sandbox.path),
                assets_dir_override=str(ref_root / "assets"),
            )
            proc = launch(repo, rv, account, settings, str(java.path),
                          on_log=lambda line, _err: log_lines.append(line))
            pid = proc.proc.pid
            emit(f"[{inst.id}] 已启动（pid={pid}），等待开始界面")
            window = wait_for_game_window(pid, timeout=timeout)
            if window is None:
                state = "进程仍存活" if proc.proc.poll() is None else f"进程已退出（{proc.proc.poll()}）"
                result.note = f"{int(timeout)}s 内未出现游戏窗口，{state}"
            else:
                result.window_title = window.title
                result.window_seconds = round(time.time() - t0, 1)
                shot_path = shots_dir / f"trial-{inst.id}.png"
                if capture_window(window.hwnd, shot_path):
                    result.screenshot = str(shot_path)
                    result.shot = screenshot_stats(shot_path)
            time.sleep(1.0)
            result.errors = _log_errors(log_lines)
            result.tail = [line.strip()[:220] for line in log_lines if line.strip()][-14:]
            crashes = sorted((sandbox.path / "crash-reports").glob("crash-*.txt"))
            if crashes:
                result.crash = crashes[-1].name
            alive = proc.proc.poll() is None
            exited = proc.proc.poll()
            result.ok = bool(
                window is not None
                and not result.errors
                and not result.crash
                and (result.shot.get("ok") is not False)
            )
            if not alive:
                result.note = result.note or f"进程已退出（代码 {exited}）"
                if exited in (0, None) and window is not None:
                    result.ok = result.ok and not result.errors
        except Exception as exc:  # noqa: BLE001
            result.note = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                if proc is not None and proc.proc.poll() is None:
                    kill_tree(proc.proc.pid)
                    proc.proc.wait(timeout=15)
            except Exception:  # noqa: BLE001
                pass
            if not keep:
                pass  # 沙箱保留，便于事后排查；清理由 CLI --clean 负责
            result.seconds = round(time.time() - t0, 1)
            status = "通过" if result.ok else "未通过"
            emit(f"[{inst.id}] {status}（{result.seconds}s）{result.note}")

    run.seconds = round(time.time() - started, 1)
    after = fingerprint(ref_root)
    run.diff = diff_fingerprints(before, after)
    return run


def render_report(run: TrialRun) -> str:
    """生成 Markdown 报告。"""
    lines = ["# 参考实例试运行报告", ""]
    lines.append(f"- 参考目录：`{run.reference_root}`")
    lines.append(f"- 实例数：{len(run.results)}（可运行 {run.runnable}），通过：{run.passed}")
    lines.append(f"- 总耗时：{run.seconds}s")
    changed = run.diff.get("changed") or []
    added = run.diff.get("added") or []
    removed = run.diff.get("removed") or []
    lines.append(f"- 参考目录改动：新增 {len(added)}，删除 {len(removed)}，修改 {len(changed)}")
    lines.append("")
    lines.append("| 实例 | 结果 | 耗时 | 窗口标题 | 截图 | 说明 |")
    lines.append("|---|---|---|---|---|---|")
    for r in run.results:
        if r.skipped:
            status = "⏭️ 跳过"
        else:
            status = "✅ 通过" if r.ok else "❌ 未通过"
        shot = r.shot
        shot_text = ""
        if shot.get("unique") is not None:
            shot_text = f"{shot.get('unique')} 色 / 亮度 {shot.get('brightness')}"
        note = (r.note or "").replace("|", "/")
        if r.skipped:
            note = "不可运行：" + note
        lines.append(f"| {r.id} | {status} | {r.seconds:.1f}s | {r.window_title or '-'} | {shot_text or '-'} | {note or '-'} |")
    lines.append("")
    problems = [r for r in run.results if not r.ok and not r.skipped]
    if problems:
        lines.append("## 未通过详情")
        for r in problems:
            lines.append(f"### {r.id}")
            lines.append(f"- 说明：{r.note or '未知'}")
            if r.errors:
                lines.append("- 日志异常：")
                for e in r.errors:
                    lines.append(f"  - `{e}`")
            if r.crash:
                lines.append(f"- 崩溃报告：{r.crash}")
            if r.tail:
                lines.append("- 日志尾部：")
                for item in r.tail:
                    lines.append(f"  - `{item}`")
            lines.append("")
    if added or removed or changed:
        lines.append("## ⚠️ 参考目录发生改动（不应出现）")
        for key in ("added", "removed", "changed"):
            items = run.diff.get(key) or []
            if items:
                lines.append(f"- {key}（{len(items)}）：" + ", ".join(items[:10]))
    return "\n".join(lines)
