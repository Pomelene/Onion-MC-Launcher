"""Read-only snapshot of original F-drive files, used to audit validation writes."""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = Path(r"F:\.minecraft")
OUT = ROOT / "backups" / "f-drive-before.json"


def scan():
    files = {}
    for base, dirs, names in os.walk(GAME, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_junction()]
        for name in names:
            p = Path(base) / name
            stat = p.stat()
            key = str(p.relative_to(GAME))
            files[key] = [stat.st_size, stat.st_mtime_ns]
    return files


if __name__ == "__main__":
    if "--compare" in sys.argv:
        before = json.loads(OUT.read_text(encoding="utf-8"))
        now = scan()
        changed = [k for k, v in before.items() if now.get(k) != v]
        result = {"original_files": len(before), "changed_or_removed": changed,
                  "added_count": len(now.keys() - before.keys())}
        (ROOT / "docs" / "managed-preservation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    else:
        if OUT.exists():
            raise FileExistsError("Baseline already exists; refusing to replace it")
        files = scan()
        OUT.write_text(json.dumps(files, ensure_ascii=False), encoding="utf-8")
        print(f"Recorded {len(files)} original files")
