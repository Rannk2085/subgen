"""
核心：调本地 subconverter 把订阅 URL 转成 Clash 配置

设计：
- subgen **不再** 用 data: URI 编码订阅内容（会撞 subconverter HTTP URL 长度上限 → 414）
- 直接把原始订阅 URL 传给 subconverter，由它自己拉
- subgen 和 subconverter 在同一台机器上跑，出口 IP 完全一致，效果一样
- subconverter 默认 proxy_subscription = NONE，跟 subgen 的「始终直连」策略一致

subgen 仍然要做一次 HTTP 探测（HEAD/GET）：
- 目的不是拉内容，而是从响应头里捞 Content-Disposition filename
- 那是机场自己取的订阅名（比如 "MyAirport VIP"）
- subgen 用「机场原名 + [CONV] 前缀」作为最终 filename 传给 subconverter

命名标识：
- 前缀 [CONV] 硬编码，不可配置
- 原名优先级: 1) HTTP Content-Disposition filename
              2) URL hostname 推导（兜底）
- 最终: "[CONV] 机场原名"

网络策略：
- subgen 始终直连，不读 HTTP_PROXY 环境变量
- 如需走代理：Clash Party 启用 TUN 模式 / 用 proxychains4 包装
"""
from __future__ import annotations
import re
import socket
import urllib.parse
import urllib.request
import urllib.error
from typing import NamedTuple

from process import SUBCONVERTER_PORT


# 注意：encode_data_uri 函数已删除（v0.2.2 不再用 data: URI，避免 414）


# ============================================================
#  常量：转换标识前缀（英文缩写，硬编码不可配）
# ============================================================
NAME_PREFIX = "[CONV]"   # 标记此配置为 subgen 转换产物


class FetchResult(NamedTuple):
    """拉订阅探测结果（不一定下载完整 body）"""
    success: bool
    upstream_filename: str   # 从 Content-Disposition 提取的机场原名（可能为空）
    size_hint: int           # Content-Length 头（可能为 0）
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
    例如: link01 → [CONV] link01
    幂等：已经有前缀的不重复加。
    """
    name = (original_name or "subscription").strip()
    if name.startswith(NAME_PREFIX):
        return name
    return f"{NAME_PREFIX} {name}"


# ============================================================
#  Content-Disposition 解析
# ============================================================

def _parse_content_disposition(disposition: str) -> str:
    """
    从 Content-Disposition 头里提取 filename
    支持两种格式:
      Content-Disposition: attachment; filename="MyAirport"
      Content-Disposition: attachment; filename*=UTF-8''%E6%9C%BA%E5%9C%BA
    RFC 5987 的 filename*= 优先级高于 filename=
    """
    if not disposition:
        return ""

    # 1. 优先 filename*= (RFC 5987 编码格式)
    m = re.search(r"filename\*\s*=\s*([^;]+)", disposition, re.IGNORECASE)
    if m:
        value = m.group(1).strip()
        # 格式: charset'lang'percent_encoded_value
        parts = value.split("'", 2)
        if len(parts) == 3:
            charset, _lang, encoded = parts
            try:
                return urllib.parse.unquote(encoded, encoding=charset or "utf-8").strip()
            except Exception:
                pass

    # 2. 回退 filename=
    m = re.search(r'filename\s*=\s*"([^"]+)"', disposition, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"filename\s*=\s*([^;]+)", disposition, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"').strip("'")

    return ""


# ============================================================
#  拉订阅探测（只读响应头，捕获机场取的名字）
# ============================================================

def fetch_subscription_info(
    url: str,
    user_agent: str = "ClashMetaForAndroid/2.11.0.Meta",
    timeout: float = 15.0,
) -> FetchResult:
    """
    探测订阅 URL，只为了：
      1. 验证 URL 可达 + 不是错误页
      2. 从 Content-Disposition 头里捕获机场原名

    不下载完整 body（HEAD 请求；某些机场不支持 HEAD 时回退到 GET 但只读 1KB）。
    始终直连，不读 HTTP_PROXY 环境变量。
    """
    handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(handler)

    headers_to_send = {"User-Agent": user_agent}

    # ---- 先尝试 HEAD ----
    try:
        req = urllib.request.Request(url, method="HEAD", headers=headers_to_send)
        with opener.open(req, timeout=timeout) as resp:
            disposition = resp.headers.get("Content-Disposition", "")
            length = int(resp.headers.get("Content-Length", "0") or 0)
            return FetchResult(
                success=True,
                upstream_filename=_parse_content_disposition(disposition),
                size_hint=length,
                error="",
            )
    except urllib.error.HTTPError as e:
        # 405 = Method Not Allowed，回退到 GET
        if e.code != 405:
            body = e.read().decode("utf-8", errors="ignore")[:200] if hasattr(e, 'read') else ""
            return FetchResult(False, "", 0, f"HEAD HTTP {e.code}: {e.reason} - {body}")
    except urllib.error.URLError as e:
        return FetchResult(False, "", 0, f"HEAD 网络错误: {e.reason}")
    except (OSError, socket.timeout) as e:
        return FetchResult(False, "", 0, f"HEAD 超时: {e}")

    # ---- HEAD 405 → GET 兜底，只读首部不读 body ----
    try:
        req = urllib.request.Request(url, headers=headers_to_send)
        with opener.open(req, timeout=timeout) as resp:
            disposition = resp.headers.get("Content-Disposition", "")
            length = int(resp.headers.get("Content-Length", "0") or 0)
            # 读 1 KB 验证连接 OK，不下载完整 body
            try:
                resp.read(1024)
            except Exception:
                pass
            return FetchResult(
                success=True,
                upstream_filename=_parse_content_disposition(disposition),
                size_hint=length,
                error="",
            )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:200] if hasattr(e, 'read') else ""
        return FetchResult(False, "", 0, f"GET HTTP {e.code}: {e.reason} - {body}")
    except urllib.error.URLError as e:
        return FetchResult(False, "", 0, f"GET 网络错误: {e.reason}")
    except (OSError, socket.timeout) as e:
        return FetchResult(False, "", 0, f"GET 超时: {e}")


# ============================================================
#  URL 构造
# ============================================================

def build_convert_url(
    subscription_url: str,
    target: str = "clash",
    config_url: str = "",
    filename: str = "",
    extra_params: dict | None = None,
) -> str:
    """
    构造调用本地 subconverter 的完整 URL

    把原始订阅 URL 直接作为 url= 参数传给 subconverter（不再 base64 编码）。
    subconverter 会自己拉这个 URL（同机器同 IP，跟 subgen 直连效果一致）。

    filename 通过 &filename= 传给 subconverter，subconverter 在响应头里设
        Content-Disposition: attachment; filename=...
    支持的客户端（Clash for Windows / Mihomo Party 等）导入时会用作默认配置名。
    """
    params = {
        "target": target,
        "url": subscription_url,
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
    config_url: str,
    target: str = "clashmeta",
) -> tuple[FetchResult, ConvertResult, str]:
    """
    完整流程：探测订阅头 → 拼接 subconverter URL → 调 subconverter
    返回 (fetch_result, convert_result, final_filename)

    final_filename 优先级：
      1. HTTP Content-Disposition 头里的 filename（机场自己取的原名）
      2. URL hostname 推导（兜底）
      然后 + [CONV] 前缀
    """
    # 1. 探测订阅 URL，捞 Content-Disposition filename + 验证可达
    fetch = fetch_subscription_info(subscription_url)

    # 2. 决定最终 filename
    if fetch.success and fetch.upstream_filename:
        # 用机场自己取的名字
        original_name = fetch.upstream_filename
    else:
        # 兜底：从 URL 推导
        original_name = derive_name_from_url(subscription_url)
    final_filename = make_filename(original_name)

    # 3. 如果探测都失败了，没必要再调 subconverter
    if not fetch.success:
        return (
            fetch,
            ConvertResult(False, "", "", 0, 0, 0, f"订阅探测失败: {fetch.error}"),
            final_filename,
        )

    # 4. 构造 subconverter URL（直接传订阅 URL，不用 data: URI）
    convert_url = build_convert_url(
        subscription_url,
        target=target,
        config_url=config_url,
        filename=final_filename,
    )

    # 5. 调本地 subconverter
    result = call_subconverter(convert_url)
    return fetch, result, final_filename
