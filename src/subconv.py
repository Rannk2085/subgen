"""
核心：拉订阅 → base64 → data: URI → 调本地 subconverter 生成转换 URL

技术要点（来自 Agent 3 调研）：
- subconverter 支持 data:text/plain;base64,... URL scheme
- 我们用 Python 用任意网络拉订阅，再 base64 喂进去
- 这样可以「每订阅独立选网络」而不需要修改 subconverter 配置
- 缺点：data: URI 是快照，Clash Party 拿到的内容是固定的，需要重新跑 subgen 才能更新

命名标识：
- subconverter 支持 &filename= 参数，会写到 Content-Disposition 响应头
- Clash for Windows / Mihomo Party 等客户端导入订阅时会用作默认配置名
- 我们自动加一个固定的英文缩写前缀 [SG]，区分「这是 subgen 转换出来的配置」
- 前缀不可配置，硬编码为 [SG]
"""
from __future__ import annotations
import base64
import json
import socket
import urllib.parse
import urllib.request
import urllib.error
from typing import NamedTuple

from process import SUBCONVERTER_PORT


# ============================================================
#  常量：转换标识前缀（英文缩写，硬编码不可配）
# ============================================================
NAME_PREFIX = "[SG]"   # SubGen 缩写，标记此配置为 subgen 转换产物


class FetchResult(NamedTuple):
    success: bool
    content: bytes
    size: int
    error: str


class ConvertResult(NamedTuple):
    success: bool
    url: str
    yaml_content: str
    proxy_count: int
    rule_count: int
    group_count: int
    error: str


# subconverter 的常用 query 参数
DEFAULT_QUERY_PARAMS = {
    "insert": "false",
    "emoji": "true",
    "list": "false",
    "tfo": "false",
    "scv": "false",
    "fdn": "false",
    "sort": "false",
    "new_name": "true",
}


# ============================================================
#  名字推导
# ============================================================

def derive_name_from_url(url: str) -> str:
    """
    从订阅 URL 推导一个友好名字。
    - https://link01.nobodys.uk/api/...     → link01
    - https://my.airport.example.com/...    → my
    - https://sub.tagss.pro/api/clash       → sub.tagss
    """
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        if not host:
            return "subscription"
        if host.startswith("www."):
            host = host[4:]
        parts = host.split(".")
        if len(parts) >= 3:
            return f"{parts[0]}.{parts[1]}"
        if len(parts) >= 2:
            return parts[0]
        return host
    except Exception:
        return "subscription"


def make_filename(original_name: str) -> str:
    """
    把原始名字 + 标识前缀 = Clash 导入后看到的配置名
    例如: link01 → [SG] link01
    幂等：已经有前缀的不重复加。
    """
    name = (original_name or "subscription").strip()
    if name.startswith(NAME_PREFIX):
        return name
    return f"{NAME_PREFIX} {name}"


# ============================================================
#  拉订阅
# ============================================================

def fetch_subscription(
    url: str,
    network_mode: str,        # DIRECT | PROXY | CUSTOM
    custom_proxy: str = "",
    user_agent: str = "ClashMetaForAndroid/2.11.0.Meta",
    timeout: float = 30.0,
) -> FetchResult:
    """用指定网络模式拉取订阅原始内容。"""
    handlers = []

    if network_mode == "DIRECT":
        handlers.append(urllib.request.ProxyHandler({}))
    elif network_mode == "PROXY":
        proxy = "http://127.0.0.1:7890"
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    elif network_mode == "CUSTOM":
        if not custom_proxy:
            return FetchResult(False, b"", 0, "CUSTOM 模式但未提供 proxy URL")
        handlers.append(urllib.request.ProxyHandler({"http": custom_proxy, "https": custom_proxy}))
    else:
        return FetchResult(False, b"", 0, f"未知网络模式: {network_mode}")

    opener = urllib.request.build_opener(*handlers)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with opener.open(req, timeout=timeout) as resp:
            content = resp.read()
            return FetchResult(True, content, len(content), "")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:200] if hasattr(e, 'read') else ""
        return FetchResult(False, b"", 0, f"HTTP {e.code}: {e.reason} - {body}")
    except urllib.error.URLError as e:
        return FetchResult(False, b"", 0, f"网络错误: {e.reason}")
    except (OSError, socket.timeout) as e:
        return FetchResult(False, b"", 0, f"超时或连接失败: {e}")


# ============================================================
#  data: URI 编码 + URL 构造
# ============================================================

def encode_data_uri(content: bytes) -> str:
    """
    把订阅内容编码为 data:text/plain;base64,... URI
    subconverter 看到这个 URI 后会直接 base64 解码使用，不发起任何网络请求。
    """
    b64 = base64.b64encode(content).decode("ascii")
    return f"data:text/plain;base64,{b64}"


def build_convert_url(
    subscription_payload: str,    # 可以是原始 URL 或 data: URI
    target: str = "clash",
    config_url: str = "",
    filename: str = "",
    extra_params: dict | None = None,
) -> str:
    """
    构造调用本地 subconverter 的完整 URL

    filename 通过 &filename= 传给 subconverter，subconverter 会在响应头里设
        Content-Disposition: attachment; filename=...
    支持的客户端（Clash for Windows / Mihomo Party 等）导入时会用作默认配置名。
    """
    params = {
        "target": target,
        "url": subscription_payload,
    }
    if config_url:
        params["config"] = config_url
    if filename:
        params["filename"] = filename
    params.update(DEFAULT_QUERY_PARAMS)
    if extra_params:
        params.update(extra_params)

    qs = urllib.parse.urlencode(params)
    return f"http://127.0.0.1:{SUBCONVERTER_PORT}/sub?{qs}"


# ============================================================
#  调用本地 subconverter
# ============================================================

def call_subconverter(convert_url: str, timeout: float = 90.0) -> ConvertResult:
    """调用本地 subconverter 完成转换，返回结果。"""
    try:
        # 本地调用，禁用所有代理
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(convert_url, timeout=timeout) as resp:
            yaml_text = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:500] if hasattr(e, 'read') else ""
        return ConvertResult(False, "", "", 0, 0, 0, f"subconverter HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        return ConvertResult(False, "", "", 0, 0, 0, f"调用 subconverter 失败: {e.reason}")
    except (OSError, socket.timeout) as e:
        return ConvertResult(False, "", "", 0, 0, 0, f"超时: {e}")

    if not yaml_text or len(yaml_text) < 100:
        return ConvertResult(False, "", yaml_text, 0, 0, 0,
                             f"subconverter 返回过短（{len(yaml_text)} bytes）: {yaml_text[:200]}")

    proxy_count = _count_proxies(yaml_text)
    rule_count = _count_rules(yaml_text)
    group_count = _count_groups(yaml_text)

    if proxy_count == 0:
        return ConvertResult(False, "", yaml_text, 0, 0, 0,
                             f"YAML 中没有节点（前 200 字: {yaml_text[:200]}）")

    return ConvertResult(True, convert_url, yaml_text, proxy_count, rule_count, group_count, "")


def _count_proxies(yaml_text: str) -> int:
    count = 0
    in_proxies = False
    for line in yaml_text.split("\n"):
        stripped = line.lstrip()
        if line.startswith("proxies:"):
            in_proxies = True
            continue
        if in_proxies:
            if line and not line[0].isspace() and not line.startswith("#"):
                in_proxies = False
                continue
            if stripped.startswith("- {") or stripped.startswith("- name:"):
                count += 1
    return count


def _count_rules(yaml_text: str) -> int:
    count = 0
    in_rules = False
    for line in yaml_text.split("\n"):
        if line.startswith("rules:"):
            in_rules = True
            continue
        if in_rules:
            if line and not line[0].isspace() and not line.startswith("#"):
                in_rules = False
                continue
            stripped = line.lstrip()
            if stripped.startswith("- ") and any(
                stripped[2:].startswith(p) for p in
                ("DOMAIN", "IP-CIDR", "GEOIP", "MATCH", "RULE-SET", "PROCESS-NAME", "SRC-IP-CIDR")
            ):
                count += 1
    return count


def _count_groups(yaml_text: str) -> int:
    count = 0
    in_groups = False
    for line in yaml_text.split("\n"):
        if line.startswith("proxy-groups:"):
            in_groups = True
            continue
        if in_groups:
            if line and not line[0].isspace() and not line.startswith("#"):
                in_groups = False
                continue
            stripped = line.lstrip()
            if stripped.startswith("- name:") or stripped.startswith("- {"):
                count += 1
    return count


# ============================================================
#  顶层入口
# ============================================================

def generate(
    subscription_url: str,
    network_mode: str,
    custom_proxy: str,
    config_url: str,
    target: str = "clash",
) -> tuple[FetchResult, ConvertResult, str]:
    """
    完整流程：拉订阅 → 编码 → 调 subconverter
    返回 (fetch_result, convert_result, final_filename)

    final_filename 是 Clash 导入后看到的配置名 = [SG] + 原本名字
    （原本名字从订阅 URL 自动推导，不可配置）
    """
    # 计算最终文件名（即使 fetch 失败也要返回，方便日志）
    original_name = derive_name_from_url(subscription_url)
    final_filename = make_filename(original_name)

    fetch = fetch_subscription(subscription_url, network_mode, custom_proxy)
    if not fetch.success:
        return (
            fetch,
            ConvertResult(False, "", "", 0, 0, 0, "未拉到订阅，跳过转换"),
            final_filename,
        )

    data_uri = encode_data_uri(fetch.content)
    convert_url = build_convert_url(
        data_uri,
        target=target,
        config_url=config_url,
        filename=final_filename,
    )
    result = call_subconverter(convert_url)
    return fetch, result, final_filename
