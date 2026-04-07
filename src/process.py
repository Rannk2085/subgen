"""
subconverter 子进程管理（ephemeral 模式）
- 每次 subgen 启动 subconverter 作为子进程
- subgen 主进程持有 Popen 对象
- 命令跑完后 terminate / kill 清理
- 不再使用 PID 文件、不再支持 systemd 风格状态查询
"""
from __future__ import annotations
import socket
import subprocess
import time

from env import (
    SUBCONVERTER_LOG, SUBCONVERTER_DIR,
    LOGS_DIR, is_windows, subconverter_binary_path
)


SUBCONVERTER_PORT = 25500


# =================================================================
#  端口探测
# =================================================================

def is_port_listening(port: int = SUBCONVERTER_PORT) -> bool:
    """探测 TCP 端口是否在监听 (用于等待 subconverter 启动)"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except (OSError, socket.timeout):
        return False


# =================================================================
#  启动（阻塞，直到端口监听或超时）
# =================================================================

def start_blocking(timeout: float = 10.0) -> tuple[bool, "subprocess.Popen | None", str]:
    """
    阻塞启动 subconverter，等端口监听完成后返回。
    返回 (success, process, message)
    """
    # 1. 端口占用检查
    if is_port_listening(SUBCONVERTER_PORT):
        return False, None, f"端口 {SUBCONVERTER_PORT} 已被占用"

    binary = subconverter_binary_path()
    if not binary.exists():
        return False, None, f"subconverter 二进制不存在: {binary}"

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        log_fp = open(SUBCONVERTER_LOG, "ab", buffering=0)
    except OSError as e:
        return False, None, f"无法打开日志文件: {e}"

    # 确保二进制可执行
    if not is_windows():
        try:
            mode = binary.stat().st_mode
            binary.chmod(mode | 0o755)
        except OSError:
            pass

    popen_kwargs: dict = {
        "cwd": str(SUBCONVERTER_DIR),
        "stdout": log_fp,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }

    if is_windows():
        CREATE_NO_WINDOW = 0x08000000
        popen_kwargs["creationflags"] = CREATE_NO_WINDOW
    else:
        popen_kwargs["start_new_session"] = True

    # 2. 启动子进程
    try:
        proc = subprocess.Popen([str(binary)], **popen_kwargs)
    except OSError as e:
        log_fp.close()
        return False, None, f"启动失败: {e}"

    # 3. 轮询端口监听，每 100ms 检查一次
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # 如果进程提前退出，立即失败
        if proc.poll() is not None:
            return False, None, (
                f"subconverter 启动后立即退出 (exit {proc.returncode})，"
                f"查日志: {SUBCONVERTER_LOG}"
            )
        if is_port_listening(SUBCONVERTER_PORT):
            return True, proc, f"已启动 (pid {proc.pid})"
        time.sleep(0.1)

    # 4. 超时：kill 掉
    stop(proc)
    return False, None, (
        f"启动超时（{timeout}s 内端口 {SUBCONVERTER_PORT} 未监听），"
        f"查日志: {SUBCONVERTER_LOG}"
    )


# =================================================================
#  停止
# =================================================================

def stop(proc: "subprocess.Popen") -> None:
    """优雅停止 subconverter 子进程：SIGTERM → 等 5 秒 → SIGKILL"""
    if proc is None:
        return
    if proc.poll() is not None:
        return

    try:
        proc.terminate()
    except OSError:
        pass

    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        proc.kill()
    except OSError:
        pass

    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
