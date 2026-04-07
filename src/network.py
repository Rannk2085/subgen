"""
网络连通性检测 + 用户教学提示

设计要点：
- subgen 不主动改任何系统配置
- subgen 始终直连拉订阅，不读 HTTP_PROXY 环境变量
- 用户如果需要走代理，要么启用 Clash Party 的 TUN/系统代理，要么用 proxychains4 包装
- 本模块只负责：测试参考网站的 TCP 连通性、渲染快照、给出教学提示
"""
from __future__ import annotations
import socket
import time
from typing import NamedTuple


class SiteCheck(NamedTuple):
    """单个站点的连通性检测结果"""
    name: str         # 显示名 (e.g., "google.com")
    reachable: bool   # TCP 是否能连上
    latency_ms: int   # 连接耗时（毫秒）, 失败则 0


class NetSnapshot(NamedTuple):
    """当前网络连通性快照"""
    sites: list[SiteCheck]     # 每个参考站点的检测结果


# ========================================================================
#  参考站点 TCP 连通性检测
# ========================================================================

# 测试用参考站点：(显示名, host, port)
# - github.com: subgen 拉 ACL4SSR 规则要用
# - google.com: 海外标志
# - baidu.com:  国内标志
REFERENCE_SITES: list[tuple[str, str, int]] = [
    ("github.com", "github.com", 443),
    ("google.com", "google.com", 443),
    ("baidu.com",  "www.baidu.com", 443),
]


def check_site_tcp(host: str, port: int, timeout: float = 1.5) -> tuple[bool, int]:
    """
    探测站点 TCP 连通性。
    返回 (是否可达, 耗时毫秒)。失败返回 (False, 0)。
    用 socket 连接，不发 HTTP 请求，速度最快。
    """
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, int((time.monotonic() - start) * 1000)
    except (OSError, socket.timeout):
        return False, 0


def detect_env() -> NetSnapshot:
    """
    检测参考站点的 TCP 连通性。
    用于让用户判断当前网络是否能拉到他需要的资源。
    最坏 3 个站点 × 1.5 秒 = 4.5 秒，但实际多数 < 1 秒。
    """
    sites: list[SiteCheck] = []
    for name, host, port in REFERENCE_SITES:
        reachable, latency = check_site_tcp(host, port, timeout=1.5)
        sites.append(SiteCheck(name=name, reachable=reachable, latency_ms=latency))
    return NetSnapshot(sites=sites)


def render_snapshot(snap: NetSnapshot) -> str:
    """格式化输出连通性快照（多行字符串，给交互向导用）"""
    from env import C  # 延迟导入避免循环

    lines = [f"  subgen 网络模式:    {C.GREEN}直连 (始终如此){C.RESET}"]
    lines.append("")
    lines.append(f"  {C.dim('参考站点 TCP 连通性测试:')}")
    for s in snap.sites:
        if s.reachable:
            lines.append(f"    {C.GREEN}✓{C.RESET} {s.name:<15} {C.dim(f'{s.latency_ms} ms')}")
        else:
            lines.append(f"    {C.RED}✗{C.RESET} {s.name:<15} {C.dim('不可达 (timeout/拒绝)')}")

    return "\n".join(lines)


def get_proxy_setup_notes() -> list[str]:
    """
    返回给用户的「教学」性质的提示列表。
    告诉用户 subgen 的网络策略，以及如何让 subgen 走代理（如果需要）。
    每条已带颜色，可直接打印。
    """
    from env import C  # 延迟导入避免循环

    notes: list[str] = []

    notes.append(C.info("subgen 始终直连拉订阅，不读取 HTTP_PROXY/HTTPS_PROXY 环境变量"))
    notes.append(C.dim("    → 这是为了行为可预测：你看到什么 IP，subgen 就用什么 IP"))
    notes.append("")
    notes.append(C.info("如果你的订阅域名被墙，需要让 subgen 走代理，有两种方法："))
    notes.append("")

    # 方法 A
    notes.append(C.info("  方法 A: Clash Party 启用 TUN 模式 (推荐)"))
    notes.append(C.dim("    步骤: Clash Party → 设置 → 启用 TUN 模式 / 系统代理"))
    notes.append(C.dim("    效果: 所有进程的 TCP 流量都被 Clash Party 接管，包括 subgen"))
    notes.append(C.dim("          走代理还是直连由 Clash Party 的规则决定"))
    notes.append("")

    # 方法 B
    notes.append(C.info("  方法 B: 用 proxychains4 包装运行 subgen"))
    notes.append(C.dim("    命令: proxychains4 ./subgen"))
    notes.append(C.dim("    前置: sudo apt install proxychains4"))
    notes.append(C.dim("          并配置 /etc/proxychains4.conf 指向你的本地代理端口"))
    notes.append("")

    notes.append(C.warn("如果订阅域名要求特定地区 IP（比如国内地域机场）："))
    notes.append(C.dim("    → 请先在 Clash Party 切到对应地区的节点，再跑 subgen"))

    return notes
