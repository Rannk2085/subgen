"""
网络环境检测 + 建议
设计要点：
- subgen 不主动改任何系统配置
- 只检测当前状态、给出推荐、附带注意事项
- 用户自己去 Clash Party / 系统设置切换全局/规则模式
"""
from __future__ import annotations
import json
import os
import socket
import urllib.request
import urllib.error
from typing import NamedTuple


class NetSnapshot(NamedTuple):
    """当前网络环境快照"""
    sys_proxy_env: str           # HTTP_PROXY/HTTPS_PROXY 环境变量值（可能为空）
    clash_port_open: bool        # 127.0.0.1:7890 是否在监听
    clash_port: int              # 实际探测到的端口（默认 7890）
    direct_ip: str               # 直连出口 IP（无代理）
    direct_region: str           # 直连出口地域（"中国大陆" / "海外"/"未知"）
    proxy_ip: str                # 走代理的出口 IP（如果代理可用）
    proxy_region: str            # 走代理的出口地域


def check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """探测 TCP 端口是否在监听"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def fetch_outgoing_ip(proxy_url: str | None = None, timeout: float = 5.0) -> tuple[str, str]:
    """
    获取出口 IP 和地域。
    proxy_url=None 表示直连，否则走指定代理。
    返回 (ip, region)。失败返回 ("", "")。
    """
    # 用一个简单的 IP 探测服务（无认证、轻量、JSON 返回）
    candidates = [
        "https://api.myip.com",          # {ip, country, cc}
        "https://ipinfo.io/json",        # {ip, country, region, city}
        "https://api.ip.sb/geoip",       # {ip, country, ...}
    ]

    handlers: list = []
    if proxy_url:
        proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        handlers.append(proxy_handler)
    else:
        # 显式禁用环境变量代理（确保真"直连"）
        handlers.append(urllib.request.ProxyHandler({}))

    opener = urllib.request.build_opener(*handlers)

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
    """把国家代码/名称归一化为「中国大陆」/「海外」/「未知」"""
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


def detect_env(probe_proxy: bool = False, proxy_url: str = "http://127.0.0.1:7890") -> NetSnapshot:
    """
    完整检测当前网络环境。
    probe_proxy=True 时也会尝试走 proxy_url 检测出口 IP（耗时多 5s 左右）
    """
    # 1. 系统代理环境变量
    sys_proxy = os.environ.get("HTTPS_PROXY", "") or os.environ.get("HTTP_PROXY", "") \
                or os.environ.get("https_proxy", "") or os.environ.get("http_proxy", "")

    # 2. Clash Party 端口探测
    clash_port = 7890
    clash_open = check_port("127.0.0.1", clash_port, timeout=0.5)

    # 3. 直连出口 IP
    direct_ip, direct_region = fetch_outgoing_ip(proxy_url=None, timeout=5.0)

    # 4. 代理出口 IP（可选，慢）
    proxy_ip, proxy_region = "", ""
    if probe_proxy and clash_open:
        proxy_ip, proxy_region = fetch_outgoing_ip(proxy_url=proxy_url, timeout=8.0)

    return NetSnapshot(
        sys_proxy_env=sys_proxy,
        clash_port_open=clash_open,
        clash_port=clash_port,
        direct_ip=direct_ip,
        direct_region=direct_region,
        proxy_ip=proxy_ip,
        proxy_region=proxy_region,
    )


def render_snapshot(snap: NetSnapshot) -> str:
    """格式化输出环境快照（多行字符串，给交互向导用）"""
    from env import C  # 延迟导入避免循环

    lines = []
    lines.append(f"  系统代理 (env):    {snap.sys_proxy_env or C.dim('未设置')}")
    if snap.clash_port_open:
        lines.append(f"  本地代理端口:      {C.GREEN}127.0.0.1:{snap.clash_port} 监听中{C.RESET}")
    else:
        lines.append(f"  本地代理端口:      {C.dim(f'127.0.0.1:{snap.clash_port} 未监听')}")

    if snap.direct_ip:
        marker = C.GREEN if "中国" in snap.direct_region else C.YELLOW
        lines.append(f"  直连出口 IP:       {snap.direct_ip} ({marker}{snap.direct_region}{C.RESET})")
    else:
        lines.append(f"  直连出口 IP:       {C.dim('检测失败')}")

    if snap.proxy_ip:
        marker = C.YELLOW if "中国" in snap.proxy_region else C.GREEN
        lines.append(f"  代理出口 IP:       {snap.proxy_ip} ({marker}{snap.proxy_region}{C.RESET})")

    return "\n".join(lines)


def suggest_mode(snap: NetSnapshot) -> tuple[str, str]:
    """
    根据快照给出推荐模式 + 推荐理由。
    返回 (推荐 mode, 一句话理由)。mode ∈ {DIRECT, PROXY}
    """
    # 规则:
    # - 直连出口 IP 在中国大陆 → 默认 DIRECT（适合国内地域机场）
    # - 直连出口 IP 在海外 → 你已经在墙外，DIRECT 也是访问海外，PROXY 反而多一跳
    # - 直连失败但代理可用 → PROXY
    if snap.direct_region == "中国大陆":
        return "DIRECT", "你的直连出口在国内，适合拉国内地域机场（如 TAGSS）"
    if "海外" in snap.direct_region:
        return "DIRECT", "你已经在海外网络，直连即可"
    if not snap.direct_ip and snap.clash_port_open:
        return "PROXY", "直连失败，但本地代理可用"
    return "DIRECT", "无法判断，默认使用直连"


def get_mode_notes(mode: str, snap: NetSnapshot) -> list[str]:
    """
    返回某个模式的「使用注意事项」列表（每条一行字符串，已带颜色）
    """
    from env import C
    notes: list[str] = []

    if mode == "DIRECT":
        if snap.sys_proxy_env:
            notes.append(C.warn(f"你的 shell 环境有 HTTP_PROXY={snap.sys_proxy_env}"))
            notes.append(C.dim("    → 直连模式会忽略它，但请确认这是预期"))
        if snap.direct_region == "中国大陆":
            notes.append(C.ok("你当前直连出口是国内 IP，TAGSS 等国内地域机场会接受"))
        elif "海外" in snap.direct_region:
            notes.append(C.warn("你当前直连出口是海外 IP，国内地域机场会拒绝"))
            notes.append(C.dim("    → 如果是海外机场就没事，国内机场需要在 Clash Party 切到国内节点"))
        notes.append(C.info("拉订阅前确认 Clash Party 不在『全局模式』，或者你的订阅域名走的是直连规则"))

    elif mode == "PROXY":
        if not snap.clash_port_open:
            notes.append(C.fail(f"127.0.0.1:{snap.clash_port} 没在监听 - Clash Party 没启动"))
            notes.append(C.dim("    → 请先启动 Clash Party 再选这个模式"))
        else:
            notes.append(C.ok(f"127.0.0.1:{snap.clash_port} 监听中"))
        if snap.proxy_ip:
            notes.append(C.info(f"代理出口 IP: {snap.proxy_ip} ({snap.proxy_region})"))
            if snap.proxy_region == "中国大陆":
                notes.append(C.warn("代理出口也是国内 - 等于走了一圈又回国内，意义不大"))
            else:
                notes.append(C.ok("代理出口是海外 - 适合拉海外专属机场"))
        notes.append(C.info("如果是国内地域机场，请先在 Clash Party 切换到国内节点再使用此模式"))

    elif mode == "CUSTOM":
        notes.append(C.info("输入格式: http://host:port 或 socks5://host:port"))
        notes.append(C.info("常见: http://127.0.0.1:7890 / http://127.0.0.1:1080 / socks5://127.0.0.1:1080"))

    return notes
