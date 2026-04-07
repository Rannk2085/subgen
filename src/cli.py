"""
命令行解析与子命令路由（ephemeral 模式）
需要 subconverter 的命令会在主进程内启动子进程，命令结束后自动停止。
"""
from __future__ import annotations
import sys

import process
from env import C, ensure_dirs, enable_windows_ansi, subconverter_binary_path


HELP_TEXT = """\
subgen - 订阅转换工具 (subconverter 的交互式包装)

用法:
  ./subgen                       进入交互式向导（最常用）
  ./subgen gen <URL>             命令行模式，跳过 URL 输入
  ./subgen install               下载并安装 subconverter（首次使用）
  ./subgen install --force       强制重装
  ./subgen clean                 清空缓存和日志
  ./subgen doctor                诊断当前环境
  ./subgen version               显示版本
  ./subgen help                  显示这个帮助

subconverter 子进程：
  subgen 在跑命令时自动启动 subconverter，命令结束后自动停止。
  不需要手动 start/stop。

网络：
  subgen 始终直连拉订阅，不读 HTTP_PROXY 环境变量。
  如需走代理，请启用 Clash Party 的 TUN 模式或用 proxychains4 包装。

文件位置（全部相对项目根目录）:
  data/bin/subconverter/         subconverter 二进制
  data/config.toml               全局配置
  data/presets/                  命名预设
  data/cache/                    远程资源缓存（subgen clean 可清空）
  data/logs/                     日志（subgen clean 可清空）
"""


# =================================================================
#  不需要 subconverter 的命令
# =================================================================

def cmd_install(force: bool = False) -> int:
    """
    下载 / 重装 subconverter 二进制
    强化点：每次都查 GitHub 最新版，对比本地版本，提示是否需要 --force 重装
    """
    import os
    import downloader

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    local_installed = downloader.is_installed()
    local_version = _read_local_subconverter_version() if local_installed else None

    # 查 GitHub 最新版本（即使是已安装也要查）
    print(C.info("查询 GitHub MetaCubeX/subconverter 最新版本..."))
    rel_info = downloader.fetch_latest_release_info(proxy_url=proxy)
    if rel_info is None:
        latest_tag = None
        print(C.warn("  无法获取最新版本（GitHub 不可达）"))
        if proxy is None:
            print(C.dim("  提示: 设置 HTTPS_PROXY=http://127.0.0.1:7890 后重试"))
    else:
        latest_tag = rel_info.get("tag_name", "?")
        print(C.dim(f"  GitHub 最新: {latest_tag}"))

    if local_version:
        print(C.dim(f"  本地版本:   {local_version}"))

    # 已安装且不强制 → 比较版本
    if local_installed and not force:
        print(C.ok(f"subconverter 已安装"))
        print(C.dim(f"  路径: {downloader.subconverter_binary_path()}"))
        if latest_tag and local_version and latest_tag not in local_version:
            print(C.warn(f"  检测到新版本 {latest_tag}，本地指纹 {local_version}"))
            print(C.info(f"  升级: ./subgen install --force"))
        elif latest_tag:
            print(C.ok(f"  已是最新版本"))
        else:
            print(C.dim("  强制重装: ./subgen install --force"))
        return 0

    # 需要下载（首次或 force）
    print()
    print(C.info("准备下载 subconverter..."))
    if proxy is None:
        print(C.warn("如果 GitHub 直连超慢，可设置环境变量走代理后再跑:"))
        print(C.dim("  HTTPS_PROXY=http://127.0.0.1:7890 ./subgen install"))
    print()

    ok, msg = downloader.download(proxy_url=proxy, force=force)
    if ok:
        print(C.ok(msg))
        return 0
    print(C.fail(msg))
    return 1


def _read_local_subconverter_version() -> "str | None":
    """
    通过启动 subconverter 短暂请求 /version 获取版本。
    不启动则尝试从二进制 strings 中提取（不靠谱，跳过）。
    返回 "v0.9.2" 类的字符串，失败返回 None。
    """
    # 简单实现：调用 process.start_blocking 启动 → 拉 /version → stop
    # 但这成本太高（启动需 0.5-1.5s）。改为：直接查 cache 文件 mtime 或者跳过。
    # 实际方案：只在 subconverter 运行时才能拿到版本。
    # 折中：检查 binary 的 sha256 前缀作为「版本指纹」（不准但够用）
    import hashlib
    from env import subconverter_binary_path
    bp = subconverter_binary_path()
    if not bp.exists():
        return None
    try:
        with open(bp, "rb") as f:
            h = hashlib.sha256()
            chunk = f.read(64 * 1024)  # 只读前 64KB（足够区分版本）
            h.update(chunk)
        return f"sha256:{h.hexdigest()[:8]}"
    except OSError:
        return None


def cmd_clean() -> int:
    """
    清空 data/cache 和 data/logs 目录的内容（保留目录本身）
    增强：同时清空 subconverter 自己的内部缓存目录
    （这能强制下次 subgen 拉最新的 ACL4SSR 规则，而不是用 6 小时陈旧 cache）
    """
    from env import CACHE_DIR, LOGS_DIR, SUBCONVERTER_DIR, C
    import shutil

    # subconverter 内部 cache 目录（可能不存在）
    subconv_cache = SUBCONVERTER_DIR / "cache"

    targets = [CACHE_DIR, LOGS_DIR, subconv_cache]
    cleaned = []
    skipped = []

    for d in targets:
        if not d.exists():
            skipped.append(str(d))
            continue
        items = list(d.iterdir())
        if not items:
            skipped.append(str(d))
            continue
        for item in items:
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except OSError as e:
                print(C.warn(f"  跳过 {item}: {e}"))
        cleaned.append(str(d))

    if cleaned:
        print(C.ok("已清理:"))
        for d in cleaned:
            print(f"  {d}")
    if skipped and not cleaned:
        print(C.dim("没有需要清理的内容"))
    print(C.dim("\n下次 subgen 会强制重新拉取最新 ACL4SSR 规则"))
    return 0


def cmd_doctor() -> int:
    """详细环境诊断"""
    print()
    print(C.bold("=== subgen doctor ==="))
    print()

    from env import DATA_DIR, SUBCONVERTER_DIR, PROJECT_ROOT
    import subprocess
    import os
    from datetime import datetime

    rc = 0

    # 1. Python 版本
    print(C.bold("[1] Python"))
    py_ok = sys.version_info >= (3, 11)
    if py_ok:
        print(C.ok(f"  Python {sys.version.split()[0]} (需要 >= 3.11)"))
    else:
        print(C.fail(f"  Python {sys.version.split()[0]} 太老了，需要 >= 3.11"))
        rc = 2

    # 2. 数据目录
    print(C.bold("[2] 数据目录"))
    if DATA_DIR.exists():
        print(C.ok(f"  {DATA_DIR}"))
    else:
        print(C.warn(f"  {DATA_DIR} 不存在 (首次运行会自动创建)"))

    # 3. subconverter 二进制
    print(C.bold("[3] subconverter 二进制"))
    bp = subconverter_binary_path()
    if bp.exists():
        print(C.ok(f"  {bp}"))
        # 显示二进制大小和指纹（作为版本提示）
        try:
            size_kb = bp.stat().st_size // 1024
            fingerprint = _read_local_subconverter_version()
            print(C.dim(f"    大小: {size_kb} KB"))
            if fingerprint:
                print(C.dim(f"    指纹: {fingerprint}"))
        except OSError:
            pass
    else:
        print(C.fail(f"  未找到: {bp}"))
        print(C.info("    安装: ./subgen install"))
        rc = 2

    # 4. subconverter 内部缓存状态
    print(C.bold("[4] subconverter 内部缓存"))
    subconv_cache = SUBCONVERTER_DIR / "cache"
    if subconv_cache.exists():
        cache_files = list(subconv_cache.rglob("*"))
        cache_files = [f for f in cache_files if f.is_file()]
        if cache_files:
            # 找最旧 + 最新的文件
            mtimes = [f.stat().st_mtime for f in cache_files]
            oldest = datetime.fromtimestamp(min(mtimes))
            newest = datetime.fromtimestamp(max(mtimes))
            total_size_kb = sum(f.stat().st_size for f in cache_files) // 1024
            print(C.ok(f"  {len(cache_files)} 个文件, {total_size_kb} KB"))
            print(C.dim(f"    最旧: {oldest.strftime('%Y-%m-%d %H:%M')}"))
            print(C.dim(f"    最新: {newest.strftime('%Y-%m-%d %H:%M')}"))
            # 检查是否过期（>6h）
            import time
            age_hours = (time.time() - max(mtimes)) / 3600
            if age_hours > 6:
                print(C.warn(f"    ! 缓存已 {age_hours:.1f} 小时未更新"))
                print(C.dim(f"      → ./subgen clean 强制刷新"))
        else:
            print(C.dim("  缓存为空（下次跑 subgen 会从 0 开始拉规则）"))
    else:
        print(C.dim("  缓存目录不存在（首次跑 subgen 会创建）"))

    # 5. subgen git 状态
    print(C.bold("[5] subgen git 状态"))
    git_dir = PROJECT_ROOT / ".git"
    if git_dir.exists():
        try:
            # 当前 commit
            r = subprocess.run(
                ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0:
                current = r.stdout.strip()
                # 当前分支
                r2 = subprocess.run(
                    ["git", "-C", str(PROJECT_ROOT), "branch", "--show-current"],
                    capture_output=True, text=True, timeout=3
                )
                branch = r2.stdout.strip() if r2.returncode == 0 else "?"
                # commit 时间
                r3 = subprocess.run(
                    ["git", "-C", str(PROJECT_ROOT), "log", "-1", "--format=%cr"],
                    capture_output=True, text=True, timeout=3
                )
                age = r3.stdout.strip() if r3.returncode == 0 else "?"
                print(C.ok(f"  分支 {branch} @ {current} ({age})"))
                # 是否落后 remote
                r4 = subprocess.run(
                    ["git", "-C", str(PROJECT_ROOT), "status", "-sb"],
                    capture_output=True, text=True, timeout=3
                )
                if r4.returncode == 0 and "behind" in r4.stdout:
                    print(C.warn(f"    ! 本地落后远程，建议 git pull"))
                elif r4.returncode == 0 and "ahead" in r4.stdout:
                    print(C.dim(f"    本地领先远程（未推送）"))
        except (subprocess.SubprocessError, FileNotFoundError):
            print(C.dim("  git 命令不可用"))
    else:
        print(C.dim("  非 git 仓库（直接下载的源码包）"))

    # 6. 网络环境
    print(C.bold("[6] 网络环境"))
    try:
        from network import detect_env, render_snapshot
        snap = detect_env()
        print(render_snapshot(snap))
    except Exception as e:
        print(C.dim(f"  (跳过网络探测: {e})"))

    print()
    if rc == 0:
        print(C.ok("一切正常"))
    elif rc == 1:
        print(C.warn("有警告，但功能可用"))
    else:
        print(C.fail("有错误，需要修复"))
    print()
    return rc


def cmd_version() -> int:
    print("subgen 0.2.0")
    return 0


def cmd_help() -> int:
    print(HELP_TEXT)
    return 0


# =================================================================
#  路由
# =================================================================

# 不需要 subconverter 的命令
NO_SUBCONV_COMMANDS = {
    "install", "version", "--version", "-v",
    "help", "--help", "-h", "clean", "doctor",
}


def route_no_subconv(cmd: "str | None", argv: list[str]) -> int:
    try:
        if cmd in ("install",):
            return cmd_install(force="--force" in argv)
        if cmd in ("version", "--version", "-v"):
            return cmd_version()
        if cmd in ("help", "--help", "-h"):
            return cmd_help()
        if cmd == "clean":
            return cmd_clean()
        if cmd == "doctor":
            return cmd_doctor()
    except KeyboardInterrupt:
        print()
        return 130
    return 1


def main(argv: list[str]) -> int:
    enable_windows_ansi()
    ensure_dirs()

    cmd = argv[0] if argv else None

    # 路由到不需要 subconverter 的命令
    if cmd in NO_SUBCONV_COMMANDS:
        return route_no_subconv(cmd, argv)

    # 默认 / gen / URL → 需要 subconverter
    # 检查二进制
    if not subconverter_binary_path().exists():
        print(C.fail("subconverter 二进制不存在"))
        print(C.info("请先运行: ./subgen install"))
        return 2

    # 启动 subconverter（ephemeral，跑完就杀）
    print(C.dim("正在启动 subconverter..."))
    ok, proc, msg = process.start_blocking(timeout=10)
    if not ok:
        print(C.fail(f"启动 subconverter 失败: {msg}"))
        print(C.info("查看日志: cat ~/subgen/data/logs/subconverter.log"))
        return 2
    print(C.dim(f"  ok {msg}"))

    try:
        import interactive
        # 跑实际命令
        if cmd is None:
            return interactive.run_wizard()
        if cmd == "gen":
            return interactive.run_wizard(initial_url=argv[1] if len(argv) > 1 else "")
        if cmd.startswith(("http://", "https://")):
            return interactive.run_wizard(initial_url=cmd)
        print(C.fail(f"未知命令: {cmd}"))
        print(C.dim("用 ./subgen help 查看用法"))
        return 1
    except KeyboardInterrupt:
        print()
        print(C.dim("[已取消]"))
        return 130
    finally:
        # 总是清理 subconverter
        process.stop(proc)
        print(C.dim("subconverter 已停止"))
