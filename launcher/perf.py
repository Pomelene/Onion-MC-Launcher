# -*- coding: utf-8 -*-
"""性能基线：对启动链路的关键路径做可复现的微基准。

只测“本地计算与文件系统”，不测网络，避免结果随网络波动。
用法：`python -m launcher.cli bench --rounds 3`。
"""

import json
import time
from pathlib import Path
from typing import Callable, Optional


def _best_ms(func: Callable[[], object], rounds: int = 3) -> float:
    best: Optional[float] = None
    for _ in range(max(1, rounds)):
        started = time.perf_counter()
        func()
        elapsed = (time.perf_counter() - started) * 1000.0
        best = elapsed if best is None else min(best, elapsed)
    return round(best, 2)


def _pick_version(repo) -> str:
    """挑一个库最多的已安装版本作为基准样本。"""
    versions = repo.list_installed()
    if not versions:
        return ""
    best, best_count = "", -1
    for vid in versions:
        try:
            count = len(repo.resolver.load_raw(vid).get("libraries") or [])
        except Exception:  # noqa: BLE001
            continue
        if count > best_count:
            best, best_count = vid, count
    return best


def run_bench(repo, rounds: int = 3) -> list[dict]:
    """返回 [{name, ms, detail}]，每一项都尽量可独立复算。"""
    from .libraries import Library
    from .ui.theme import resolve_palette
    from .worlds import list_worlds

    results: list[dict] = []
    version_id = _pick_version(repo)

    def add(name: str, ms: float, detail: str = "") -> None:
        results.append({"name": name, "ms": ms, "detail": detail})

    if version_id:
        add("解析版本 JSON（含继承合并）",
            _best_ms(lambda: repo.resolver.resolve(version_id, None), rounds), version_id)

        try:
            raw = repo.resolver.load_raw(version_id)
            libraries = [Library.from_json(item) for item in (raw.get("libraries") or [])]
            libraries = [lib for lib in libraries if lib.matches({})]
        except Exception:  # noqa: BLE001
            libraries = []
        if libraries:
            def cold() -> None:
                repo.invalidate_library_cache()
                for lib in libraries:
                    repo.resolve_library_file(lib)

            cold_ms = _best_ms(cold, 1)
            repo.invalidate_library_cache()
            for lib in libraries:
                repo.resolve_library_file(lib)
            warm_ms = _best_ms(
                lambda: [repo.resolve_library_file(lib) for lib in libraries], rounds)
            ratio = cold_ms / warm_ms if warm_ms else 0
            add("库定位（冷缓存）", cold_ms, f"{len(libraries)} 个库")
            add("库定位（热缓存）", warm_ms,
                f"{len(libraries)} 个库，快 {ratio:.1f}×")

        try:
            add("列出已安装版本", _best_ms(lambda: repo.list_installed(), rounds))
        except Exception:  # noqa: BLE001
            pass

    saves = repo.game_dir / "saves"
    if saves.is_dir():
        worlds = list_worlds(saves)
        add("扫描存档（含目录大小）", _best_ms(lambda: list_worlds(saves), rounds),
            f"{len(worlds)} 个世界")

    manifest_path = repo.game_dir / "versions" / "version_manifest_v2.json"
    if manifest_path.is_file():
        def parse_manifest() -> None:
            json.loads(manifest_path.read_text(encoding="utf-8"))

        add("解析版本清单 JSON", _best_ms(parse_manifest, rounds),
            f"{manifest_path.stat().st_size // 1024} KB")

    add("合成主题配色 ×200",
        _best_ms(lambda: [resolve_palette("dark", "blue") for _ in range(200)], rounds))
    results.extend(_bench_world_scan(rounds))
    return results


def _bench_world_scan(rounds: int = 3) -> list[dict]:
    """用合成目录对比两种目录统计方式，验证 scandir 优化。"""
    import os
    import tempfile

    from .worlds import _dir_size as scandir_size

    def rglob_size(path: Path) -> int:
        total = 0
        for entry in Path(path).rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
        return total

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for bucket in range(20):
            folder = root / f"region-{bucket}"
            folder.mkdir(parents=True, exist_ok=True)
            for index in range(150):
                (folder / f"chunk-{index}.mca").write_bytes(b"x" * 64)
        new_ms = _best_ms(lambda: scandir_size(root), rounds)
        old_ms = _best_ms(lambda: rglob_size(root), rounds)
        ratio = old_ms / new_ms if new_ms else 0
        return [{"name": "存档大小统计（合成 3000 文件）", "ms": new_ms,
                 "detail": f"scandir {new_ms}ms / rglob {old_ms}ms，快 {ratio:.1f}×"}]


def format_bench(results: list[dict]) -> str:
    """格式化基准结果（等宽表格）。"""
    if not results:
        return "没有可测项目。"
    width = max(len(item["name"]) for item in results)
    lines = [f"{'项目'.ljust(width)}  {'耗时(ms)':>9}  说明", "-" * (width + 30)]
    for item in results:
        lines.append(f"{item['name'].ljust(width)}  {item['ms']:>9.2f}  {item['detail']}")
    return "\n".join(lines)