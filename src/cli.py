"""
命令行解析与子命令路由
"""
from __future__ import annotations
import sys

from env import C, ensure_dirs, enable_windows_ansi
import process
import interactive
from storage import load_state


HELP_TEXT = """\
subgen - 订阅转换工具 (subconverter 的交互式包装)

用法:
  ./subgen                       进入交互式向导（最常用）
  ./subgen gen <URL>             命令行模式，跳过 URL 输入
  ./subgen status                查看 subconverter 服务状态
  ./subgen start                 启动 subconverter 后台服务
  ./subgen stop                  停止 subconverter
  ./subgen restart               重启 subconverter
  ./subgen install               下载并安装 subconverter（首次使用）
  ./subgen doctor                诊断当前环境
  ./subgen version               显示版本信息
  ./subgen help                  显示这个帮助

环境变量:
  SUBGEN_HOME                    覆盖项目根目录（默认：subgen 文件夹本身）

文件位置（全部相对于项目根目录）:
  data/bin/subconverter/         subconverter 二进制
  data/config.toml               全局配置
  data/state.toml                上次选择记忆
  data/presets/                  命名预设
  data/cache/                    远程资源缓存
  data/logs/                     日志
  data/run/                      PID 文件
"""


def cmd_status() -> int:
    s = process.status()
    print()
    if s["running"]:
        print(C.ok(f"subconverter 运行中"))
        print(f"  PID:     {s['pid']}")
        print(f"  端口:    127.0.0.1:{s['port']} (监听中)")
        if s.get("version"):
            print(f"  版本:    {s['version']}")
    else:
        print(C.fail("subconverter 未运行"))
        if s["pid"] and not s["pid_alive"]:
            print(C.dim(f"  PID 文件残留: {s['pid']}"))
        elif not s["port_listening"]:
            print(C.dim("  端口未监听"))
        print()
        print(C.info("启动: ./subgen start"))
    print()
    return 0 if s["running"] else 1


def cmd_start() -> int:
    print(C.info("启动 subconverter..."))
    ok, msg = process.start()
    if ok:
        print(C.ok(msg))
        return 0
    print(C.fail(msg))
    return 1


def cmd_stop() -> int:
    print(C.info("停止 subconverter..."))
    ok, msg = process.stop()
    if ok:
        print(C.ok(msg))
        return 0
    print(C.fail(msg))
    return 1


def cmd_restart() -> int:
    process.stop()
    return cmd_start()


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


def cmd_doctor() -> int:
    """简易诊断"""
    print()
    print(C.bold("═══ subgen doctor ═══"))
    print()

    import downloader
    from env import subconverter_binary_path, DATA_DIR

    rc = 0

    # 1. Python 版本
    print(C.bold("[1] Python"))
    py_ok = sys.version_info >= (3, 11)
    if py_ok:
        print(C.ok(f"  Python {sys.version.split()[0]} (需要 ≥ 3.11)"))
    else:
        print(C.fail(f"  Python {sys.version.split()[0]} 太老了，需要 ≥ 3.11"))
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

    # 4. subconverter 服务
    print(C.bold("[4] subconverter 服务"))
    s = process.status()
    if s["running"]:
        print(C.ok(f"  运行中 pid={s['pid']} port={s['port']}"))
        if s.get("version"):
            print(C.dim(f"    {s['version']}"))
    else:
        print(C.warn("  未运行"))
        print(C.info("    启动: ./subgen start"))
        rc = max(rc, 1)

    # 5. 网络
    print(C.bold("[5] 网络环境"))
    from network import detect_env, render_snapshot
    snap = detect_env(probe_proxy=False)
    print(render_snapshot(snap))

    print()
    if rc == 0:
        print(C.ok("一切正常 ✨"))
    elif rc == 1:
        print(C.warn("有警告，但功能可用"))
    else:
        print(C.fail("有错误，需要修复"))
    print()
    return rc


def cmd_version() -> int:
    from . import __version__
    print(f"subgen {__version__}")
    return 0


def cmd_gen(args: list[str]) -> int:
    """命令行模式：./subgen gen <URL>"""
    if not args:
        return interactive.run_wizard()
    return interactive.run_wizard(initial_url=args[0])


def cmd_help() -> int:
    print(HELP_TEXT)
    return 0


# =================================================================
#  主分发
# =================================================================

def main(argv: list[str]) -> int:
    enable_windows_ansi()
    ensure_dirs()

    if not argv:
        # 默认进交互向导
        return interactive.run_wizard()

    cmd = argv[0]
    rest = argv[1:]

    routes = {
        "gen":     lambda: cmd_gen(rest),
        "status":  cmd_status,
        "start":   cmd_start,
        "stop":    cmd_stop,
        "restart": cmd_restart,
        "install": lambda: cmd_install(force="--force" in rest),
        "doctor":  cmd_doctor,
        "version": cmd_version,
        "--version": cmd_version,
        "-v":      cmd_version,
        "help":    cmd_help,
        "--help":  cmd_help,
        "-h":      cmd_help,
    }

    if cmd in routes:
        try:
            return routes[cmd]()
        except KeyboardInterrupt:
            print()
            print(C.dim("[已取消]"))
            return 130

    # 未知命令：可能是 URL 直传
    if cmd.startswith(("http://", "https://")):
        return interactive.run_wizard(initial_url=cmd)

    print(C.fail(f"未知命令: {cmd}"))
    print(C.dim("用 ./subgen help 查看用法"))
    return 1
