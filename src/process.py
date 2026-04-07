"""
subconverter 子进程管理（持久后台模式）
- 启动 subconverter 为 detached 进程
- PID 文件落在 data/run/
- 跨平台 stop / status
- 不依赖 systemd / launchd / schtasks
"""
from __future__ import annotations
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from env import (
    SUBCONVERTER_PID, SUBCONVERTER_LOG, SUBCONVERTER_DIR,
    LOGS_DIR, RUN_DIR, is_windows, subconverter_binary_path
)


SUBCONVERTER_PORT = 25500


# =================================================================
#  PID 文件
# =================================================================

def _read_pid() -> int:
    if not SUBCONVERTER_PID.exists():
        return 0
    try:
        return int(SUBCONVERTER_PID.read_text().strip())
    except (OSError, ValueError):
        return 0


def _write_pid(pid: int) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    SUBCONVERTER_PID.write_text(str(pid))


def _clear_pid() -> None:
    if SUBCONVERTER_PID.exists():
        try:
            SUBCONVERTER_PID.unlink()
        except OSError:
            pass


# =================================================================
#  进程检查（跨平台）
# =================================================================

def is_pid_alive(pid: int) -> bool:
    """跨平台检测 PID 是否存活"""
    if pid <= 0:
        return False
    if is_windows():
        # Windows: 用 tasklist 查
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=3
            )
            return str(pid) in r.stdout
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    else:
        # POSIX: signal 0 不发任何信号，但会检查权限和存在性
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def is_port_listening(port: int = SUBCONVERTER_PORT) -> bool:
    """探测端口是否被监听（subconverter 启动完成的可靠指标）"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except (OSError, socket.timeout):
        return False


# =================================================================
#  状态查询
# =================================================================

def status() -> dict:
    """
    返回 subconverter 的运行状态:
    {
        "running": bool,         # 端口监听 + PID 存活 都满足
        "pid": int,
        "pid_alive": bool,
        "port_listening": bool,
        "port": int,
        "version": str | None,
    }
    """
    pid = _read_pid()
    pid_alive = is_pid_alive(pid)
    port_open = is_port_listening(SUBCONVERTER_PORT)

    version = None
    if port_open:
        version = _fetch_version()

    return {
        "running": port_open and pid_alive,
        "pid": pid,
        "pid_alive": pid_alive,
        "port_listening": port_open,
        "port": SUBCONVERTER_PORT,
        "version": version,
    }


def _fetch_version() -> str | None:
    """调 subconverter 的 /version 接口"""
    import urllib.request
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{SUBCONVERTER_PORT}/version",
            timeout=2
        ) as r:
            return r.read().decode("utf-8", errors="ignore").strip()
    except (OSError, Exception):
        return None


# =================================================================
#  启动
# =================================================================

def start() -> tuple[bool, str]:
    """
    启动 subconverter 子进程（持久后台模式，subgen 退出后继续运行）
    返回 (成功 bool, 信息字符串)
    """
    binary = subconverter_binary_path()
    if not binary.exists():
        return False, f"subconverter 二进制不存在: {binary}"

    # 已在跑就不重复启
    s = status()
    if s["running"]:
        return True, f"subconverter 已在运行 (pid {s['pid']}, port {s['port']})"

    # 清理可能残留的 PID 文件
    if s["pid"] and not s["pid_alive"]:
        _clear_pid()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_fp = open(SUBCONVERTER_LOG, "ab", buffering=0)

    # 确保 binary 可执行
    if not is_windows():
        try:
            mode = binary.stat().st_mode
            binary.chmod(mode | 0o755)
        except OSError:
            pass

    # 平台相关参数
    popen_kwargs = {
        "cwd": str(SUBCONVERTER_DIR),
        "stdout": log_fp,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }

    if is_windows():
        # Windows: detach 控制台、自己的进程组
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000
        popen_kwargs["creationflags"] = (
            DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        )
    else:
        # POSIX: setsid 让子进程成为新会话 leader，父进程退出后存活
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen([str(binary)], **popen_kwargs)
    except OSError as e:
        log_fp.close()
        return False, f"启动失败: {e}"

    _write_pid(proc.pid)

    # 等待端口监听（最多 5 秒）
    for _ in range(50):
        if is_port_listening(SUBCONVERTER_PORT):
            return True, f"已启动 (pid {proc.pid}, port {SUBCONVERTER_PORT})"
        time.sleep(0.1)

    # 超时但进程还活着
    if is_pid_alive(proc.pid):
        return False, f"进程已启动但端口未监听超时（pid {proc.pid}），查日志: {SUBCONVERTER_LOG}"
    return False, f"进程启动后立即退出，查日志: {SUBCONVERTER_LOG}"


# =================================================================
#  停止
# =================================================================

def stop() -> tuple[bool, str]:
    """优雅停止 subconverter（SIGTERM → 等待 → SIGKILL）"""
    pid = _read_pid()
    if not pid:
        return True, "subconverter 未运行（无 PID 文件）"

    if not is_pid_alive(pid):
        _clear_pid()
        return True, f"PID {pid} 已不存在，清理 PID 文件"

    if is_windows():
        # Windows: taskkill /F /PID
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=5
            )
        except subprocess.SubprocessError as e:
            return False, f"taskkill 失败: {e}"
    else:
        # POSIX: SIGTERM → 等 5s → SIGKILL
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as e:
            return False, f"SIGTERM 失败: {e}"
        for _ in range(50):
            if not is_pid_alive(pid):
                break
            time.sleep(0.1)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    _clear_pid()
    return True, f"已停止 (pid {pid})"


# =================================================================
#  确保运行（懒启动 helper）
# =================================================================

def ensure_running() -> tuple[bool, str]:
    """
    幂等：如果在跑就什么都不做，没在跑就拉起。
    供「每次 subgen 命令都先调一次」使用。
    """
    s = status()
    if s["running"]:
        return True, f"已在运行 (pid {s['pid']})"
    return start()
