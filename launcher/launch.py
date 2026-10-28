# -*- coding: utf-8 -*-
"""启动 Minecraft：构建命令行、替换占位符、启动并监听进程。

命令行结构：
    <java> [JVM 参数] <mainClass> [游戏参数]
占位符（如 ${auth_player_name}）在参数中统一替换；未知占位符保持原样。
"""

import os
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .repository import GameRepository
from .version import ResolvedVersion
from .paths import LAUNCHER_NAME,LAUNCHER_VERSION

_PLACEHOLDER_RE = re.compile(r"\$\{(.*?)\}")


@dataclass
class Account:
    """启动使用的账号信息（离线与正版共用）。"""

    username: str
    uuid: str
    access_token: str = "0"
    user_type: str = "legacy"
    authlib_url: str = ""        # 外置登录服务器地址（authlib 类型使用）
    client_id: str = ""
    xuid: str = ""


@dataclass
class LaunchSettings:
    """一次启动的可调参数。"""

    java_path: str = ""
    min_memory: int = 2048
    max_memory: int = 4096
    width: int = 854
    height: int = 480
    fullscreen: bool = False
    demo: bool = False
    server_address: str = ""
    extra_jvm_args: list[str] = field(default_factory=list)
    extra_game_args: list[str] = field(default_factory=list)
    process_priority: str = "normal"
    pre_launch_command: str = ""
    post_exit_command: str = ""
    launcher_name: str = LAUNCHER_NAME
    launcher_version: str = LAUNCHER_VERSION
    authlib_injector_jar: str = ""   # authlib-injector.jar 本地路径（外置登录时使用）
    game_dir_override: str = ""      # 覆盖 --gameDir（试运行时指向沙箱）
    assets_dir_override: str = ""    # 覆盖 --assetsDir（指向只读参考目录）


def substitute(value: str, placeholders: dict) -> str:
    """替换 ${name} 形式的占位符；缺失的保持原样（与 HMCL 一致）。"""
    return _PLACEHOLDER_RE.sub(lambda m: str(placeholders.get(m.group(1), m.group(0))), value)


def build_classpath(repo: GameRepository, rv: ResolvedVersion) -> str:
    """classpath：适用的非原生库 + 客户端 jar，按顺序拼接。"""
    entries: list[str] = []
    seen: set[str] = set()
    for lib in rv.libraries:
        if not lib.matches() or lib.is_native():
            continue
        path, _origin = repo.resolve_library_file(lib)
        if path is None:
            continue
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            entries.append(str(path))
    jar = repo.client_jar_path(rv)
    if jar.exists() and str(jar).lower() not in seen:
        entries.append(str(jar))
    return os.pathsep.join(entries)


def game_features(settings: LaunchSettings) -> dict:
    """供规则求值使用的 features。"""
    return {
        "has_custom_resolution": bool(settings.width and settings.height),
        "is_demo_user": bool(settings.demo),
    }


def _version_at_least(version_id: str, major: int, minor: int) -> bool:
    """粗略比较版本号（仅用于判断 1.20+ 之类的特性差异）。"""
    m = re.match(r"(\d+)\.(\d+)", version_id or "")
    if not m:
        return False
    return (int(m.group(1)), int(m.group(2))) >= (major, minor)


def build_command(repo: GameRepository, rv: ResolvedVersion, account: Account,
                  settings: LaunchSettings, java_path: str) -> list[str]:
    """构建完整命令行参数列表。"""
    if settings.min_memory <= 0 or settings.max_memory < settings.min_memory:
        raise ValueError("内存设置无效：最大内存不能小于最小内存，且必须大于 0")
    run_dir = Path(settings.game_dir_override) if settings.game_dir_override else repo.run_dir(rv.id)
    assets_dir = Path(settings.assets_dir_override) if settings.assets_dir_override else repo.assets_dir
    natives_dir = repo.natives_dir(rv.id)
    classpath = build_classpath(repo, rv)
    client_jar = repo.client_jar_path(rv)
    log_config = repo.logging_config_path(rv, search_dir=assets_dir)

    placeholders = {
        "auth_player_name": account.username,
        "auth_uuid": account.uuid.replace("-", ""),
        "auth_access_token": account.access_token or "0",
        "auth_session": account.access_token or "0",
        "clientid": account.client_id,
        "auth_xuid": account.xuid,
        "user_type": account.user_type,
        "version_name": rv.id,
        "profile_name": "Minecraft",
        "version_type": rv.type,
        "game_directory": str(run_dir),
        "assets_root": str(assets_dir),
        "game_assets": str(assets_dir),
        "assets_index_name": rv.asset_index_id,
        "natives_directory": str(natives_dir),
        "launcher_name": settings.launcher_name,
        "launcher_version": settings.launcher_version,
        "classpath": classpath,
        "classpath_separator": os.pathsep,
        "library_directory": str(repo.libraries_dir),
        "libraries_directory": str(repo.libraries_dir),
        "primary_jar": str(client_jar),
        "primary_jar_name": client_jar.name,
        "user_properties": "{}",
        "resolution_width": str(settings.width),
        "resolution_height": str(settings.height),
        "file_separator": os.sep,
        "language": "zh-CN",
    }

    command: list[str] = [java_path]

    # ---- JVM 参数 ----
    mem = [f"-Xms{int(settings.min_memory)}M", f"-Xmx{int(settings.max_memory)}M"]
    command += mem
    if settings.extra_jvm_args:
        command += [str(a) for a in settings.extra_jvm_args]

    jvm_from_manifest = [substitute(a, placeholders) for a in rv.jvm_args]
    command += jvm_from_manifest

    def has_option(prefix: str) -> bool:
        return any(a.startswith(prefix) for a in command)

    if not has_option("-Djava.library.path="):
        command.append(f"-Djava.library.path={natives_dir}")
    if not has_option("-Dminecraft.launcher.brand="):
        command.append(f"-Dminecraft.launcher.brand={settings.launcher_name}")
    if not has_option("-Dminecraft.launcher.version="):
        command.append(f"-Dminecraft.launcher.version={settings.launcher_version}")
    if not has_option("-Dminecraft.client.jar="):
        command.append(f"-Dminecraft.client.jar={client_jar}")
    if settings.authlib_injector_jar and account.authlib_url:
        if not any(a.startswith("-javaagent:") for a in command):
            command.append(f"-javaagent:{settings.authlib_injector_jar}={account.authlib_url}")
    if log_config is not None and not has_option("-Dlog4j.configurationFile="):
        command.append(f"-Dlog4j.configurationFile={log_config}")

    if not has_option("-cp") and not has_option("-classpath"):
        command += ["-cp", classpath]

    # ---- 主类 ----
    command.append(rv.main_class)

    # ---- 游戏参数 ----
    if rv.minecraft_args:
        game = [substitute(a, placeholders) for a in shlex.split(rv.minecraft_args)]
    else:
        game = [substitute(a, placeholders) for a in rv.game_args]

    if settings.width and settings.height and "--width" not in game:
        game += ["--width", str(settings.width), "--height", str(settings.height)]
    if settings.fullscreen and "--fullscreen" not in game:
        game.append("--fullscreen")
    if settings.demo and "--demo" not in game:
        game.append("--demo")
    if settings.server_address and "--server" not in game and "--quickPlayMultiplayer" not in game:
        address = settings.server_address.strip()
        if _version_at_least(getattr(rv, "client_version_id", "") or rv.id, 1, 20):
            game += ["--quickPlayMultiplayer", address]
        else:
            host, _, port = address.partition(":")
            game += ["--server", host]
            if port:
                game += ["--port", port]
    game += [str(a) for a in settings.extra_game_args]
    command += game
    return command


class ManagedProcess:
    """带日志转发的游戏进程。"""

    def __init__(self, proc: subprocess.Popen, on_log: Optional[Callable[[str, bool], None]],
                 on_exit: Optional[Callable[[int], None]]):
        self.proc = proc
        self._on_log = on_log
        self._on_exit = on_exit
        self.started_at = time.time()
        self._threads: list[threading.Thread] = []
        self._start_pumps()

    def _start_pumps(self) -> None:
        for stream, is_error in ((self.proc.stdout, False), (self.proc.stderr, True)):
            if stream is None:
                continue
            t = threading.Thread(target=self._pump, args=(stream, is_error), daemon=True)
            t.start()
            self._threads.append(t)
        waiter = threading.Thread(target=self._wait, daemon=True)
        waiter.start()

    def _pump(self, stream, is_error: bool) -> None:
        try:
            from .crash import redact
            discarding=False
            for raw in iter(lambda:stream.readline(256*1024), b""):
                complete=raw.endswith(b'\n')
                if discarding:
                    discarding=not complete;continue
                if len(raw)==256*1024 and not complete:
                    discarding=True
                    if self._on_log:self._on_log('[日志行过长，已省略]',is_error)
                    continue
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if self._on_log:
                    self._on_log(redact(line), is_error)
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _wait(self) -> None:
        code = self.proc.wait()
        for t in self._threads:
            t.join(timeout=3)
        if self._on_exit:
            self._on_exit(code)

    def stop(self) -> None:
        """结束游戏进程（尽量连同子进程）。"""
        if self.proc.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            self.proc.terminate()


def _pid_alive(pid: int) -> bool:
    """判断进程是否仍在运行（用于清理陈旧的实例锁）。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        # Do not infer that a process is dead from an unavailable/localized
        # tasklist command: that could clear a live lock and corrupt an instance.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such PID
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class InstanceLock:
    """同版本单实例锁（基于锁文件 + PID 存活探测）。"""

    def __init__(self, path: Path):
        self.path = path
        self.owner_pid = os.getpid()

    def acquire(self) -> bool:
        if self.path.exists():
            try:
                pid = int(self.path.read_text(encoding="utf-8").strip() or "0")
            except (OSError, ValueError):
                pid = 0
            if _pid_alive(pid):
                return False
            # 陈旧锁：清理后重新获取
            try:
                self.path.unlink()
            except OSError:
                return False
        try:
            with self.path.open("x", encoding="utf-8") as stream:
                stream.write(str(os.getpid()))
            return True
        except OSError:
            return False

    def release(self) -> None:
        try:
            if self.path.exists() and self.path.read_text(encoding="utf-8").strip() == str(self.owner_pid):
                self.path.unlink()
        except OSError:
            pass


def launch(repo: GameRepository, rv: ResolvedVersion, account: Account,
           settings: LaunchSettings, java_path: str,
           on_log: Optional[Callable[[str, bool], None]] = None,
           on_exit: Optional[Callable[[int], None]] = None, cancel=None) -> ManagedProcess:
    """启动游戏并返回受管进程（不等待游戏退出）。"""
    if account.user_type in ('msa','mojang') and account.access_token in ('','0'):
        raise PermissionError('在线账号凭据不可用，请重新登录后启动')
    command = build_command(repo, rv, account, settings, java_path)
    run_dir = Path(settings.game_dir_override) if settings.game_dir_override else repo.run_dir(rv.id)
    if not settings.game_dir_override:
        repo.assert_writable(run_dir / ".craftbridge-run")
    run_dir.mkdir(parents=True, exist_ok=True)
    lock = InstanceLock(repo.version_dir(rv.id) / ".instance.lock")
    if not lock.acquire():
        raise RuntimeError(f"版本 {rv.id} 已在运行中，请先结束正在进行的游戏")

    env = os.environ.copy()
    if os.name == "nt":
        env["APPDATA"] = str(repo.game_dir.parent)
    env["INST_NAME"] = rv.id
    env["INST_DIR"] = str(repo.version_dir(rv.id))
    env["INST_MC_DIR"] = str(run_dir)
    env["INST_JAVA"] = java_path

    def command_args(value):
        import shlex
        return value if os.name=='nt' else shlex.split(value)

    def _wrapped_exit(code: int) -> None:
        lock.release()
        if settings.post_exit_command.strip():
            try:
                subprocess.Popen(command_args(settings.post_exit_command),cwd=str(run_dir),env=env,
                                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
            except (OSError,ValueError) as error:
                if on_log:on_log('游戏退出后命令启动失败：'+str(error),True)
        if on_exit:on_exit(code)

    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        flags |= {"below": 0x00004000, "above": 0x00008000}.get(settings.process_priority, 0)

    proc = None
    try:
        if settings.pre_launch_command.strip():
            from .download import DownloadCancelled
            before=subprocess.Popen(command_args(settings.pre_launch_command),cwd=str(run_dir),env=env,
                                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
            while True:
                try:code=before.wait(timeout=.1);break
                except subprocess.TimeoutExpired:
                    if cancel is not None and cancel.is_set():
                        before.terminate();before.wait(timeout=10);raise DownloadCancelled('启动已取消')
            if code:raise RuntimeError(f'启动前命令失败（退出码 {code}）')
        if cancel is not None and cancel.is_set():
            from .download import DownloadCancelled
            raise DownloadCancelled('启动已取消')
        proc = subprocess.Popen(
            command,
            cwd=str(run_dir),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=flags,
        )
        # Keep the game PID so the lock remains meaningful if the launcher exits.
        lock.path.write_text(str(proc.pid), encoding="utf-8")
        lock.owner_pid = proc.pid
    except Exception:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=10)
        lock.release()
        raise
    return ManagedProcess(proc, on_log, _wrapped_exit)
