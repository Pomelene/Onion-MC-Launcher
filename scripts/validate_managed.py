r"""Repeatable acceptance checks on NEW isolated instances in F:\.minecraft.

Never launches, removes, or edits original user instances/worlds.
"""
import argparse
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from launcher.config import Config
from launcher.repository import GameRepository

RESULTS = ROOT / "docs" / "managed-results.json"
BASE = "1.20.4"
PREFIX = "CraftBridge-Test-"


def stage(text):
    print(text, flush=True)


def install(repo, kind):
    if kind == "vanilla":
        target = BASE
    elif kind in ("fabric", "quilt"):
        from launcher.install.fabric import install_loader
        repo.install(BASE, stage)
        target = install_loader(repo, BASE, kind=kind, on_stage=stage)
    elif kind in ("forge", "neoforge"):
        from launcher.install.forge import install_forge
        from launcher.java import resolve_java
        java = resolve_java(17, "", repo.downloader)
        target = install_forge(repo, BASE, kind=kind, on_stage=stage, java_path=str(java.path))
    else:
        from launcher.install.optifine import install as optifine
        from launcher.java import resolve_java
        java = resolve_java(17, "", repo.downloader)
        target = optifine(repo, BASE, java_path=str(java.path), on_stage=stage)
    repo.install(target, stage)
    alias = PREFIX + kind
    if not repo.version_dir(alias).exists():
        repo.create_instance(target, alias)
    problems = repo.verify(alias, deep=True)
    if problems:
        raise RuntimeError("\n".join(problems))
    return {"base": target, "instance": alias, "deep_verify": "passed"}


def resources(repo):
    from launcher.mods import read_mod_info, set_mod_enabled, scan_mods, delete_mod
    from launcher.mods import scan_resourcepacks, scan_shaderpacks
    from launcher.saves import backup, restore, delete_save
    from launcher.safety import restore_recycled, recycle
    from launcher.modpack import export_mrpack, import_modpack
    from launcher.catalog import versions, pick_version, download_version, search
    from launcher.worlds import list_worlds
    alias = PREFIX + "fabric"
    if not repo.version_dir(alias).is_dir():
        raise RuntimeError("Install Fabric acceptance instance first")
    run = repo.run_dir(alias)
    downloads = search(repo.downloader, "mod", "fabric api", BASE, "fabric", limit=3)
    chosen = pick_version(versions(repo.downloader, "fabric-api"), BASE, "fabric")
    if not chosen:
        raise RuntimeError("No compatible Fabric API")
    path = download_version(repo.downloader, chosen, run / "mods")
    info = read_mod_info(path)
    assert info.mod_id == "fabric-api"
    disabled = set_mod_enabled(info, False)
    assert not disabled.enabled
    enabled = set_mod_enabled(disabled, True)
    assert enabled.enabled
    delete_mod(enabled)
    stored = sorted((path.parent / ".craftbridge-trash").glob("*" + path.name))[-1]
    restore_recycled(stored, path.parent)
    assert path.is_file()
    for folder in ("resourcepacks", "shaderpacks"):
        p = run / folder / "CraftBridge-Test.zip"
        p.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(p, "w") as archive:
            archive.writestr("pack.mcmeta", '{"pack":{"pack_format":22,"description":"Acceptance fixture"}}')
        scanner = scan_resourcepacks if folder == "resourcepacks" else scan_shaderpacks
        assert any(pack.path == p for pack in scanner(p.parent))
        restored = restore_recycled(recycle(p, p.parent), p.parent)
        assert restored.is_file()
    world = run / "saves" / "CraftBridge-Test-World"
    world.mkdir(parents=True, exist_ok=True)
    import gzip
    from tests.test_worlds import _tag_compound, _tag_string, _tag_int, _tag_long
    # A valid NBT fixture exercises parsing without opening or touching a user's world.
    payload = _tag_compound("", _tag_compound("Data", _tag_string("LevelName", "CraftBridge Test") + _tag_int("GameType", 1) + _tag_long("LastPlayed", 1700000000000)))
    with gzip.open(world / "level.dat", "wb") as f:
        f.write(payload)
    assert list_worlds(run / "saves")
    archive = backup(world, run / "backups")
    restored = restore(archive, run / "saves")
    assert (restored / "level.dat").read_bytes() == (world / "level.dat").read_bytes()
    delete_save(restored)
    delete_save(world)
    exported = export_mrpack(repo, alias, repo.game_dir / ".craftbridge" / "validation" / "roundtrip.mrpack",
                             name="CraftBridge-Test-Roundtrip")
    imported = import_modpack(repo, exported, stage)
    from launcher.modpack import read_modpack_info
    assert read_modpack_info(exported).loader_version == "0.19.5"
    assert (repo.mods_dir(imported) / path.name).read_bytes() == path.read_bytes()
    stored = repo.delete_version(imported)
    restore_recycled(stored, repo.versions_dir)
    return {"modrinth_hits": len(downloads.get("hits", [])), "fabric_api": path.name,
            "mod_toggle_remove_restore": "passed", "packs_remove_restore": "passed",
            "world_backup_restore": "passed", "mrpack_roundtrip": imported,
            "instance_remove_restore": "passed"}


def launch_test(repo, kind, seconds):
    from launcher.launch import launch, LaunchSettings, Account
    from launcher.accounts import offline_uuid
    from launcher.java import resolve_java
    vid = PREFIX + kind
    rv = repo.install(vid, stage)
    java = resolve_java(rv.java_major, "", repo.downloader, stage)
    settings = LaunchSettings(java_path=str(java.path), min_memory=512, max_memory=2048,
                              width=960, height=540)
    logs = []
    def log(line, is_err):
        logs.append(line)
    process = launch(repo, rv, Account("BridgeTester", offline_uuid("BridgeTester")),
                     settings, str(java.path), on_log=log)
    stage(f"RUNNING {vid} pid={process.proc.pid} java={java.major}")
    try:
        deadline = time.time() + seconds
        while time.time() < deadline and process.proc.poll() is None:
            time.sleep(0.5)
        alive = process.proc.poll() is None
        if not alive and process.proc.returncode != 0:
            raise RuntimeError("Game exited unexpectedly: " + "".join(logs[-20:]))
        return {"pid": process.proc.pid, "java": java.major, "alive_at_end": alive,
                "log": str(ROOT / "tmp" / f"managed-{kind}.log")}
    finally:
        (ROOT / "tmp" / f"managed-{kind}.log").write_text("".join(logs), encoding="utf-8")
        if process.proc.poll() is None:
            process.stop()
            process.proc.wait(timeout=20)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("install", "resources", "launch", "catalog", "verify", "curseforge"))
    parser.add_argument("--kind", default="vanilla")
    parser.add_argument("--seconds", type=int, default=120)
    args = parser.parse_args()
    repo = GameRepository(Config(ROOT / "config" / "settings.json"))
    if repo.game_dir.resolve() != Path(r"F:\.minecraft").resolve() or repo.fallback_roots:
        raise RuntimeError("Acceptance checks require the managed F-drive configuration")
    key = args.phase + "-" + args.kind
    results = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    started = time.time()
    try:
        if args.phase == "install":
            value = install(repo, args.kind)
        elif args.phase == "resources":
            value = resources(repo)
        elif args.phase == "launch":
            value = launch_test(repo, args.kind, args.seconds)
        elif args.phase == "curseforge":
            from launcher.curseforge import CurseForgeClient
            from launcher.modpack import import_modpack
            from launcher.mods import scan_mods
            client = CurseForgeClient(repo.downloader, repo.config.get("curseforge_api_key"))
            files = client.files(238222, BASE)
            chosen = next(f for f in files if "forge" in f.get("fileName", "").lower()
                          and "neoforge" not in f.get("fileName", "").lower())
            archive = repo.game_dir / ".craftbridge" / "validation" / "curseforge-test.zip"
            archive.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("manifest.json", json.dumps({"name": "CraftBridge-Test-CurseForge",
                    "version": "1", "manifestType": "minecraftModpack", "manifestVersion": 1,
                    "minecraft": {"version": BASE, "modLoaders": [{"id":"forge-49.2.13", "primary":True}]},
                    "files": [{"projectID":238222, "fileID":chosen["id"], "required":True}]}))
            target = import_modpack(repo, archive, stage)
            mods = scan_mods(repo.mods_dir(target))
            if not any(m.path.name == chosen["fileName"] for m in mods):
                raise RuntimeError("JEI was not installed")
            value = {"instance": target, "file": chosen["fileName"], "file_id": chosen["id"]}
        elif args.phase == "verify":
            import subprocess
            from launcher.launch import build_command, LaunchSettings, Account
            from launcher.accounts import offline_uuid
            from launcher.java import find_all_java
            value = {"instances": {}, "java_majors": sorted({j.major for j in find_all_java()})}
            for kind in ("vanilla", "fabric", "quilt", "forge", "neoforge", "optifine"):
                if not repo.resolver.json_path(PREFIX + kind).is_file():
                    raise RuntimeError(f"Missing acceptance instance: {kind}")
            for vid in repo.list_installed():
                rv = repo.resolver.resolve(vid)
                command = build_command(repo, rv, Account("BridgeTester", offline_uuid("BridgeTester")),
                                        LaunchSettings(server_address="localhost:25565"), "java")
                problems = repo.verify(vid, deep=vid.startswith(PREFIX))
                value["instances"][vid] = {"problems": problems,
                    "run_dir": str(repo.run_dir(vid)), "main_class": rv.main_class,
                    "command_characters": len(subprocess.list2cmdline(command)),
                    "unexpanded_placeholders": any("${" in arg for arg in command)}
                if vid.startswith(PREFIX) and (problems or any("${" in arg for arg in command)):
                    raise RuntimeError(f"Invalid test instance: {vid}: {problems}")
        else:
            from launcher.aggregator import InfoHub
            hub = InfoHub(repo.downloader)
            hub.refresh(force=True)
            value = {s.key: {"state": s.state, "error": getattr(s, "error", "")} for s in hub.status_list()}
            if any(v["state"] != "ok" for v in value.values()):
                raise RuntimeError(str(value))
        results[key] = {"status": "passed", "seconds": round(time.time() - started, 2), **value}
    except Exception as exc:
        results[key] = {"status": "failed", "error": str(exc), "seconds": round(time.time() - started, 2)}
        raise
    finally:
        current = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
        current[key] = results[key]
        from launcher.safety import write_text
        write_text(RESULTS, json.dumps(current, ensure_ascii=False, indent=2))
        print(json.dumps(results[key], ensure_ascii=False), flush=True)
