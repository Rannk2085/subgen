"""
网络环境检测 + 用户教学提示

设计要点：
- subgen 不主动改任何系统配置
- subgen 始终直连拉订阅，不读 HTTP_PROXY 环境变量
- 用户如果需要走代理，要么启用 Clash Party 的 TUN/系统代理，要么用 proxychains4 包装
- 本模块只负责：检测当前状态、渲染快照、给出教学提示
"""
from __future__ import annotations
import json
import os
import socket
import urllib.request
import urllib.error
from typing import NamedTuple


class NetSnapshot(NamedTuple):
    """当前网络环境快照（subgen 始终直连，所以只需要直连相关字段）"""
    sys_proxy_env: str           # HTTP_PROXY/HTTPS_PROXY 环境变量值（可能为空，仅作提示）
    clash_port_open: bool        # 127.0.0.1:7890 是否在监听
    clash_port: int              # 实际探测到的端口（默认 7890）
    direct_ip: str               # 直连出口 IP
    direct_region: str           # 直连出口地域（"中国大陆" / "海外·xxx" / "未知"）


def check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """探测 TCP 端口是否在监听"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def fetch_outgoing_ip(timeout: float = 5.0) -> tuple[str, str]:
    """
    获取直连出口 IP 和地域。
    始终强制直连（空 ProxyHandler），不受 HTTP_PROXY 环境变量影响。
    返回 (ip, region)。失败返回 ("", "")。
    """
    candidates = [
        "https://api.myip.com",          # {ip, country, cc}
        "https://ipinfo.io/json",        # {ip, country, region, city}
        "https://api.ip.sb/geoip",       # {ip, country, ...}
    ]

    # 强制直连：空 ProxyHandler 会覆盖默认从环境变量读 proxy 的行为
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "subgen/0.1 (curl-like)"})
            with opener.open(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                ip = data.get("ip", "")
                # 不同服务字段不同
                country = data.get("country", "") or data.get("country_code", "") or data.get("cc", "")
                region = _normalize_region(country)
                if ip:
                    return ip, region
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError, socket.timeout):
            continue

    return "", ""


def _normalize_region(country: str) -> str:
    """把国家代码/名称归一化为「中国大陆」/「海外·xxx」/「未知」"""
    if not country:
        return "未知"
    c = country.upper()
    if c in ("CN", "CHINA", "中国"):
        return "中国大陆"
    if c in ("HK", "HONG KONG", "香港"):
        return "海外·香港"
    if c in ("TW", "TAIWAN", "台湾"):
        return "海外·台湾"
    if c in ("MO", "MACAO", "MACAU"):
        return "海外·澳门"
    return f"海外·{country}"


def detect_env() -> NetSnapshot:
    """
    完整检测当前网络环境（不包含代理探测，因为 subgen 始终直连）。
    - 系统代理 env：仅作提示，subgen 不会用
    - Clash Party 端口：仅作提示，告诉用户是否开着
    - 直连出口 IP：强制直连探测（用空 ProxyHandler）
    """
    # 1. 系统代理环境变量（仅作展示用）
    sys_proxy = os.environ.get("HTTPS_PROXY", "") or os.environ.get("HTTP_PROXY", "") \
                or os.environ.get("https_proxy", "") or os.environ.get("http_proxy", "")

    # 2. Clash Party 端口探测
    clash_port = 7890
    clash_open = check_port("127.0.0.1", clash_port, timeout=0.5)

    # 3. 直连出口 IP（强制不走代理）
    direct_ip, direct_region = fetch_outgoing_ip(timeout=5.0)

    return NetSnapshot(
        sys_proxy_env=sys_proxy,
        clash_port_open=clash_open,
        clash_port=clash_port,
        direct_ip=direct_ip,
        direct_region=direct_region,
    )


def render_snapshot(snap: NetSnapshot) -> str:
    """格式化输出环境快照（多行字符串，给交互向导用）"""
    from env import C  # 延迟导入避免循环

    lines = []
    lines.append(f"  subgen 网络模式:    {C.GREEN}直连 (始终如此){C.RESET}")

    if snap.sys_proxy_env:
        lines.append(f"  系统代理 (env):     {snap.sys_proxy_env} {C.dim('(subgen 不读取)')}")
    else:
        lines.append(f"  系统代理 (env):     {C.dim('未设置')}")

    if snap.clash_port_open:
        lines.append(f"  Clash Party 端口:   {C.GREEN}127.0.0.1:{snap.clash_port} 监听中{C.RESET}")
    else:
        lines.append(f"  Clash Party 端口:   {C.dim(f'127.0.0.1:{snap.clash_port} 未监听')}")

    if snap.direct_ip:
        marker = C.GREEN if "中国" in snap.direct_region else C.YELLOW
        lines.append(f"  直连出口 IP:        {snap.direct_ip} ({marker}{snap.direct_region}{C.RESET})")
    else:
        lines.append(f"  直连出口 IP:        {C.dim('检测失败')}")

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
