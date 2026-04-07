"""
跨平台环境与路径解析
关键设计：所有路径都基于项目根目录（即 git clone 出来的 subgen/ 目录），
        不写入任何系统位置（无 XDG / AppData）
"""
from __future__ import annotations
import os
import sys
import platform
from pathlib import Path

# ----- 项目根 -----
# src/env.py 的父目录是 src/，再上一级是项目根
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# 允许 SUBGEN_HOME 环境变量覆盖（极少用）
if os.environ.get("SUBGEN_HOME"):
    PROJECT_ROOT = Path(os.environ["SUBGEN_HOME"]).resolve()

# ----- 数据目录（运行时生成，被 .gitignore） -----
DATA_DIR: Path = PROJECT_ROOT / "data"

BIN_DIR:     Path = DATA_DIR / "bin"
CACHE_DIR:   Path = DATA_DIR / "cache"
LOGS_DIR:    Path = DATA_DIR / "logs"
RUN_DIR:     Path = DATA_DIR / "run"
PRESETS_DIR: Path = DATA_DIR / "presets"

CONFIG_FILE: Path = DATA_DIR / "config.toml"
STATE_FILE:  Path = DATA_DIR / "state.toml"

SUBCONVERTER_DIR: Path = BIN_DIR / "subconverter"
SUBCONVERTER_PID: Path = RUN_DIR / "subconverter.pid"
SUBCONVERTER_LOG: Path = LOGS_DIR / "subconverter.log"
SUBGEN_LOG:       Path = LOGS_DIR / "subgen.log"


def ensure_dirs() -> None:
    """确保所有运行时目录存在。幂等。"""
    for d in (DATA_DIR, BIN_DIR, CACHE_DIR, LOGS_DIR, RUN_DIR, PRESETS_DIR, SUBCONVERTER_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ----- 平台探测 -----
def os_name() -> str:
    """linux | darwin | windows"""
    p = sys.platform
    if p.startswith("linux"):
        return "linux"
    if p == "darwin":
        return "darwin"
    if p in ("win32", "cygwin"):
        return "windows"
    return p


def arch() -> str:
    """统一架构名: amd64 / arm64 / armv7"""
    m = platform.machine().lower()
    return {
        "x86_64": "amd64",
        "amd64": "amd64",
        "i386": "i386",
        "i686": "i386",
        "aarch64": "arm64",
        "arm64": "arm64",
        "armv8l": "arm64",
        "armv7l": "armv7",
        "armv6l": "armv7",
    }.get(m, m)


def is_windows() -> bool:
    return os_name() == "windows"


def subconverter_binary_name() -> str:
    """subconverter 可执行文件名（带平台后缀）"""
    return "subconverter.exe" if is_windows() else "subconverter"


def subconverter_binary_path() -> Path:
    return SUBCONVERTER_DIR / subconverter_binary_name()


# ----- 颜色（ANSI escape，stdlib only） -----
class C:
    """简单 ANSI 颜色。如果 stdout 不是 tty，自动禁用。"""
    _enabled = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    RESET   = "\033[0m"   if _enabled else ""
    BOLD    = "\033[1m"   if _enabled else ""
    DIM     = "\033[2m"   if _enabled else ""

    RED     = "\033[31m"  if _enabled else ""
    GREEN   = "\033[32m"  if _enabled else ""
    YELLOW  = "\033[33m"  if _enabled else ""
    BLUE    = "\033[34m"  if _enabled else ""
    MAGENTA = "\033[35m"  if _enabled else ""
    CYAN    = "\033[36m"  if _enabled else ""
    GRAY    = "\033[90m"  if _enabled else ""

    @classmethod
    def ok(cls, msg: str) -> str:    return f"{cls.GREEN}✓{cls.RESET} {msg}"
    @classmethod
    def fail(cls, msg: str) -> str:  return f"{cls.RED}✗{cls.RESET} {msg}"
    @classmethod
    def warn(cls, msg: str) -> str:  return f"{cls.YELLOW}!{cls.RESET} {msg}"
    @classmethod
    def info(cls, msg: str) -> str:  return f"{cls.BLUE}→{cls.RESET} {msg}"
    @classmethod
    def dim(cls, msg: str) -> str:   return f"{cls.GRAY}{msg}{cls.RESET}"
    @classmethod
    def bold(cls, msg: str) -> str:  return f"{cls.BOLD}{msg}{cls.RESET}"


def enable_windows_ansi() -> None:
    """Windows 老版 cmd 默认不解析 ANSI，需要手动开启 VTP。"""
    if not is_windows():
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        # STD_OUTPUT_HANDLE = -11
        h = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(h, ctypes.byref(mode))
        kernel32.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass
