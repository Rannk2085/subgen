"""
subconverter 二进制下载器
- 检测当前 OS+arch
- 从 GitHub release 下载对应文件
- 解压到 data/bin/subconverter/
- 国内用户用代理（环境变量 / 配置）

镜像策略：不用镜像。直连 GitHub（如果你有代理就配代理）。
"""
from __future__ import annotations
import os
import shutil
import tarfile
import tempfile
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

from env import (
    SUBCONVERTER_DIR, BIN_DIR, os_name, arch,
    subconverter_binary_path, is_windows, C
)


# 优先使用 MetaCubeX fork（更活跃，由 mihomo 团队维护）
GITHUB_REPO = "MetaCubeX/subconverter"
GITHUB_API  = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _asset_filename() -> str | None:
    """
    根据当前 OS/arch 返回 release asset 文件名。
    映射来自 Agent 3 的实测调研：tindy2013 与 MetaCubeX 命名一致。
    """
    o = os_name()
    a = arch()

    table = {
        ("linux",   "amd64"): "subconverter_linux64.tar.gz",
        ("linux",   "i386"):  "subconverter_linux32.tar.gz",
        ("linux",   "arm64"): "subconverter_aarch64.tar.gz",
        ("linux",   "armv7"): "subconverter_armv7.tar.gz",
        ("darwin",  "amd64"): "subconverter_darwin64.tar.gz",
        ("darwin",  "arm64"): "subconverter_darwinarm.tar.gz",
        ("windows", "amd64"): "subconverter_win64.7z",
        ("windows", "i386"):  "subconverter_win32.7z",
    }
    return table.get((o, a))


def is_installed() -> bool:
    return subconverter_binary_path().exists()


def _make_opener(proxy_url: str | None):
    """构造 HTTP opener，支持代理"""
    handlers = []
    if proxy_url:
        handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def fetch_latest_release_info(proxy_url: str | None = None) -> dict | None:
    """查 GitHub API 获取最新 release 元数据"""
    import json
    opener = _make_opener(proxy_url)
    try:
        req = urllib.request.Request(
            GITHUB_API,
            headers={"User-Agent": "subgen/0.1", "Accept": "application/vnd.github+json"}
        )
        with opener.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(C.fail(f"GitHub API 请求失败: {e}"))
        return None


def can_access_github_direct(timeout: float = 6.0) -> bool:
    """
    检测当前网络是否可访问 GitHub API（强制直连，不读 HTTP(S)_PROXY）。
    用于 install 阶段决定是否提示用户配置本地代理。
    注意：若用户开启了 TUN/系统代理，此检测也会判定为可达。
    """
    opener = _make_opener(None)
    req = urllib.request.Request(
        GITHUB_API,
        headers={"User-Agent": "subgen/0.1", "Accept": "application/vnd.github+json"},
        method="HEAD",
    )
    try:
        with opener.open(req, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        # 只要收到了 HTTP 响应，就说明网络可达。
        return True
    except (urllib.error.URLError, OSError):
        return False


def download(proxy_url: str | None = None, force: bool = False) -> tuple[bool, str]:
    """
    下载并安装 subconverter 到 data/bin/subconverter/
    proxy_url=None 表示直连，否则走代理
    """
    if is_installed() and not force:
        return True, f"已存在: {subconverter_binary_path()}"

    asset_name = _asset_filename()
    if asset_name is None:
        return False, f"不支持的平台: {os_name()}/{arch()}"

    if asset_name.endswith(".7z"):
        return False, "Windows 用 .7z 压缩，subgen 当前未实现 7z 解压。请手动下载并解压到 data/bin/subconverter/"

    print(C.info(f"获取 MetaCubeX/subconverter 最新 release..."))
    rel = fetch_latest_release_info(proxy_url)
    if rel is None:
        return False, "无法获取 release 信息（GitHub 不可达）"

    tag = rel.get("tag_name", "?")
    print(C.info(f"  最新版本: {tag}"))

    # 找到对应的 asset
    asset = None
    for a in rel.get("assets", []):
        if a.get("name") == asset_name:
            asset = a
            break

    if asset is None:
        return False, f"release {tag} 中找不到 {asset_name}"

    download_url = asset.get("browser_download_url")
    size = asset.get("size", 0)
    print(C.info(f"  下载 {asset_name} ({size // 1024} KB)..."))

    # 下载到临时文件
    opener = _make_opener(proxy_url)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = BIN_DIR / f".{asset_name}.downloading"

    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": "subgen/0.1"})
        with opener.open(req, timeout=120) as resp:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        if tmp_path.exists():
            tmp_path.unlink()
        return False, f"下载失败: {e}"

    actual_size = tmp_path.stat().st_size
    if actual_size < 1000:
        tmp_path.unlink()
        return False, f"下载文件太小 ({actual_size} bytes)，可能不完整"

    print(C.ok(f"  下载完成 ({actual_size} bytes)"))

    # 解压
    SUBCONVERTER_DIR.mkdir(parents=True, exist_ok=True)
    print(C.info(f"  解压到 {SUBCONVERTER_DIR}..."))

    try:
        with tarfile.open(tmp_path, "r:gz") as tar:
            # 解压到临时目录，再 move（避免污染目标目录）
            with tempfile.TemporaryDirectory(dir=BIN_DIR) as tmp_extract:
                tar.extractall(tmp_extract, filter='data')

                # release 包内是 subconverter/ 目录，把内容平移到 SUBCONVERTER_DIR
                src_dir = Path(tmp_extract) / "subconverter"
                if not src_dir.exists():
                    return False, "解压后没找到 subconverter/ 目录"

                # 清空目标目录
                for item in SUBCONVERTER_DIR.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

                # 移动内容
                for item in src_dir.iterdir():
                    shutil.move(str(item), str(SUBCONVERTER_DIR / item.name))

    except (tarfile.TarError, OSError) as e:
        return False, f"解压失败: {e}"
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    # 加可执行权限
    if not is_windows():
        bp = subconverter_binary_path()
        if bp.exists():
            bp.chmod(0o755)

    # 把 pref.toml 的 cache_config 改成 0（每次都重新拉 ini，避免 5 分钟陈旧）
    _patch_pref_toml()

    return True, f"已安装 {tag} 到 {SUBCONVERTER_DIR}"


def _patch_pref_toml() -> None:
    """
    安装/重装后修改 subconverter 的 pref.toml:
      - cache_config = 0   每次重新拉 ini 配置（不缓存 5 分钟）
    其他默认值保持不变。
    """
    pref = SUBCONVERTER_DIR / "pref.toml"
    if not pref.exists():
        return
    try:
        text = pref.read_text(encoding="utf-8")
        new = text.replace("cache_config = 300", "cache_config = 0")
        if new != text:
            pref.write_text(new, encoding="utf-8")
            print(C.dim("  已设置 cache_config = 0 (每次拉新 ini)"))
    except OSError:
        pass


def copy_existing(source_dir: Path) -> tuple[bool, str]:
    """
    从已存在的 subconverter 目录复制（用于本地开发，避免重复下载）
    source_dir 应该是包含 subconverter 二进制和 base/ 目录的目录
    """
    src_binary = source_dir / ("subconverter.exe" if is_windows() else "subconverter")
    if not src_binary.exists():
        return False, f"源目录无 subconverter 二进制: {src_binary}"

    SUBCONVERTER_DIR.mkdir(parents=True, exist_ok=True)
    for item in SUBCONVERTER_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    for item in source_dir.iterdir():
        if item.name == "data" or item.name.startswith("."):
            continue
        if item.is_dir():
            shutil.copytree(item, SUBCONVERTER_DIR / item.name)
        else:
            shutil.copy2(item, SUBCONVERTER_DIR / item.name)

    if not is_windows():
        bp = subconverter_binary_path()
        if bp.exists():
            bp.chmod(0o755)

    return True, f"已从 {source_dir} 复制"
