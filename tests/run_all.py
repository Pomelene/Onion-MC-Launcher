# -*- coding: utf-8 -*-
"""测试运行器：收集 tests/ 下 test_*.py 中的 test_* 函数并执行，写出报告。"""

import importlib
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))


def main() -> int:
    modules = sorted(HERE.glob("test_*.py"))
    passed = failed = 0
    failures = []
    started = time.time()
    print(f"运行 {len(modules)} 个测试模块……\n")
    for m in modules:
        mod = importlib.import_module(m.stem)
        tests = [n for n in dir(mod) if n.startswith("test_") and callable(getattr(mod, n))]
        for name in sorted(tests):
            t0 = time.time()
            try:
                getattr(mod, name)()
                passed += 1
                print(f"  PASS  {m.stem}.{name}  ({time.time()-t0:.2f}s)")
            except Exception:
                failed += 1
                tb = traceback.format_exc()
                failures.append((m.stem, name, tb))
                print(f"  FAIL  {m.stem}.{name}")
                print(tb)

    total = passed + failed
    elapsed = time.time() - started
    lines = [
        "# CraftBridge 测试报告（单元 / 集成）",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 通过：{passed} / {total}",
        f"- 失败：{failed}",
        f"- 耗时：{elapsed:.2f}s",
        "",
    ]
    if failures:
        lines.append("## 失败详情")
        lines.append("")
        for mod, name, tb in failures:
            lines.append(f"### {mod}.{name}")
            lines.append("```")
            lines.append(tb.rstrip())
            lines.append("```")
            lines.append("")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "test-report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n=== 通过 {passed} / {total}，失败 {failed}，耗时 {elapsed:.2f}s ===")
    print("报告已写入 docs/test-report.md")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
