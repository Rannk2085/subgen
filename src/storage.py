"""
TOML 配置 / 预设 持久化
- 读 TOML：用 stdlib tomllib (Python 3.11+)
- 写 TOML：自己实现的简易 serializer，支持平铺 [section] + 字符串/数字/bool/列表
- 原子写：临时文件 + os.replace
"""
from __future__ import annotations
import os
import tomllib
from pathlib import Path
from typing import Any

from env import CONFIG_FILE, PRESETS_DIR


# =================================================================
#  TOML 简易 writer（够 subgen 用，不是通用 TOML 库）
# =================================================================

def _format_value(v: Any) -> str:
    """把 Python 值转成 TOML 字面量。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int) or isinstance(v, float):
        return str(v)
    if isinstance(v, str):
        # 转义反斜杠和双引号
        s = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'
    if isinstance(v, list):
        return "[" + ", ".join(_format_value(x) for x in v) + "]"
    if v is None:
        return '""'
    raise TypeError(f"unsupported TOML value type: {type(v).__name__}")


def dumps(data: dict[str, Any]) -> str:
    """
    把字典序列化为 TOML 文本。
    支持嵌套一层（{section: {k: v}}），不支持嵌套表数组等高级特性。
    顶层裸键（非 dict 值）会先输出，再输出 [section] 段。
    """
    lines: list[str] = []

    # 1. 先输出顶层裸键
    bare_keys = [(k, v) for k, v in data.items() if not isinstance(v, dict)]
    for k, v in bare_keys:
        lines.append(f"{k} = {_format_value(v)}")

    if bare_keys:
        lines.append("")

    # 2. 输出每个 [section]
    sections = [(k, v) for k, v in data.items() if isinstance(v, dict)]
    for sec_name, sec_data in sections:
        lines.append(f"[{sec_name}]")
        for k, v in sec_data.items():
            if isinstance(v, dict):
                # 嵌套表用 [section.subsection]
                lines.append("")
                lines.append(f"[{sec_name}.{k}]")
                for k2, v2 in v.items():
                    lines.append(f"{k2} = {_format_value(v2)}")
            else:
                lines.append(f"{k} = {_format_value(v)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def loads(text: str) -> dict[str, Any]:
    """parse TOML text → dict（用 stdlib tomllib）"""
    return tomllib.loads(text)


# =================================================================
#  原子写入
# =================================================================

def atomic_write(path: Path, content: str) -> None:
    """同目录 tmp + os.replace，跨平台原子写。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# =================================================================
#  Config 读写
# =================================================================

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "general": {
        # 默认规则套餐 ID（参考 src/presets_data.py 里的 PRESETS）
        "default_preset_id": "Full",
        # 默认目标客户端（注意 subconverter 没有 'clashmeta' target，
        # Clash 全家共用 'clash'，输出的 YAML 兼容 Clash.Meta / Mihomo / Clash Party）
        "default_target": "clash",
    },
    "subconverter": {
        "port": 25500,
    },
}


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return DEFAULT_CONFIG.copy()


def save_config(cfg: dict[str, Any]) -> None:
    atomic_write(CONFIG_FILE, dumps(cfg))


# =================================================================
#  Presets 命名预设
# =================================================================

def list_presets() -> list[str]:
    """返回所有预设的名字（不含 .toml 后缀）"""
    if not PRESETS_DIR.exists():
        return []
    return sorted(p.stem for p in PRESETS_DIR.glob("*.toml"))


def load_preset(name: str) -> dict[str, Any] | None:
    p = PRESETS_DIR / f"{name}.toml"
    if not p.exists():
        return None
    try:
        with open(p, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def save_preset(name: str, data: dict[str, Any]) -> Path:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    p = PRESETS_DIR / f"{name}.toml"
    atomic_write(p, dumps(data))
    return p


def delete_preset(name: str) -> bool:
    p = PRESETS_DIR / f"{name}.toml"
    if p.exists():
        p.unlink()
        return True
    return False
