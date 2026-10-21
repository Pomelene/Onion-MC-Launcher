"""Exercise current restore code inside the existing F-drive acceptance instance only."""
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from launcher.config import Config
from launcher.repository import GameRepository
from launcher.saves import backup, restore
from launcher.safety import recycle


def main():
    repo = GameRepository(Config(ROOT / "config" / "settings.json"))
    if repo.game_dir.resolve() != Path(r"F:\.minecraft").resolve():
        raise RuntimeError("Acceptance requires F-drive management")
    instance = repo.version_dir("CraftBridge-Test-vanilla")
    if not (instance / ".isolate").is_file():
        raise RuntimeError("Expected existing isolated acceptance instance")
    repo.assert_idle(instance.name)
    saves = repo.saves_dir(instance.name)
    world = repo.assert_writable(saves / f"CraftBridge-Restore-Test-{uuid.uuid4().hex[:8]}")
    world.mkdir(parents=True, exist_ok=False)
    (world / "level.dat").write_bytes(b"restore-acceptance-fixture")
    archive = backup(world, instance / "backups")
    created = [world]
    with patch("launcher.saves.time.strftime", return_value="same-second"):
        first = restore(archive, saves)
        created.append(first)
        (first / "level.dat").write_bytes(b"changed-after-first-restore")
        second = restore(archive, saves)
        created.append(second)
    assert len(set(created)) == 3
    assert (world / "level.dat").read_bytes() == b"restore-acceptance-fixture"
    assert (first / "level.dat").read_bytes() == b"changed-after-first-restore"
    assert (second / "level.dat").read_bytes() == b"restore-acceptance-fixture"
    stored = [str(recycle(path, saves)) for path in created]
    result = {"status": "passed", "instance": instance.name,
              "repeated_restore_preserves_existing_data": True,
              "test_fixtures_recycled": stored, "backup": str(archive)}
    (ROOT / "docs" / "restore-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Restore acceptance passed; all three synthetic worlds moved to recovery storage.")


if __name__ == "__main__":
    main()
