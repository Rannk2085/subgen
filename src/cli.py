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
    import downloader
    if downloader.is_installed() and not force:
        print(C.ok(f"subconverter 已安装"))
        print(C.dim(f"  路径: {downloader.subconverter_binary_path()}"))
        print(C.dim("  强制重装: ./subgen install --force"))
        return 0

    print(C.info("准备下载 subconverter..."))
    print(C.warn("如果 GitHub 直连超慢，可设置环境变量走代理后再跑:"))
    print(C.dim("  HTTPS_PROXY=http://127.0.0.1:7890 ./subgen install"))
    print()

    import os
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    ok, msg = downloader.download(proxy_url=proxy, force=force)
    if ok:
        print(C.ok(msg))
        return 0
    print(C.fail(msg))
    return 1


def cmd_clean() -> int:
    """清空 data/cache 和 data/logs 目录的内容（保留目录本身）"""
    from env import CACHE_DIR, LOGS_DIR, C
    import shutil

    cleaned = []
    for d in (CACHE_DIR, LOGS_DIR):
        if d.exists():
            for item in d.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            cleaned.append(str(d))

    if cleaned:
        print(C.ok("已清理:"))
        for d in cleaned:
            print(f"  {d}")
    else:
        print(C.dim("没有需要清理的内容"))
    return 0


def cmd_doctor() -> int:
    """简易诊断"""
    print()
    print(C.bold("=== subgen doctor ==="))
    print()

    from env import DATA_DIR

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
    else:
        print(C.fail(f"  未找到: {bp}"))
        print(C.info("    安装: ./subgen install"))
        rc = 2

    # 4. 网络环境
    print(C.bold("[4] 网络环境"))
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
