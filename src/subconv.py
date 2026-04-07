"""
核心：拉订阅 → 起本地 HTTP 服务器 → 让 subconverter 从本地 socket 拉 → 转换

为什么要起本地 HTTP 服务器（v0.2.5 设计）：
- v0.1: 用 data: URI base64 编码内容嵌入 URL → 大订阅撞 subconverter 414 (URI Too Long)
- v0.2.2-v0.2.4: 直接传订阅原 URL 给 subconverter → subconverter 用自己的 UA 拉，
  某些机场只接受 Clash 系 UA，subconverter 拿到错误页 → 'No nodes were found!'
- v0.2.5: subgen 用 ClashMeta UA 拉到完整内容 → 在 127.0.0.1:RANDOM 起一个临时 HTTP 服务器
  → 把 http://127.0.0.1:RANDOM/sub 传给 subconverter → subconverter 从本地 socket 拉
  → 同时解决 414（URL 短）和 UA 问题（我们决定服务器响应内容）

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
import http.server
import re
import socket
import threading
import urllib.parse
import urllib.request
import urllib.error
from contextlib import contextmanager
from typing import Iterator, NamedTuple

from process import SUBCONVERTER_PORT


# ============================================================
#  常量：转换标识前缀（英文缩写，硬编码不可配）
# ============================================================
NAME_PREFIX = "[CONV]"   # 标记此配置为 subgen 转换产物


class FetchResult(NamedTuple):
    """拉订阅完整结果"""
    success: bool
    content: bytes              # 完整订阅内容（用于喂本地 HTTP 服务器）
    upstream_filename: str      # 从 Content-Disposition 提取的机场原名（可能为空）
    size: int                   # len(content)
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
#  拉订阅（GET 完整内容 + 捕获 Content-Disposition）
# ============================================================

def fetch_subscription(
    url: str,
    user_agent: str = "ClashMetaForAndroid/2.11.0.Meta",
    timeout: float = 30.0,
) -> FetchResult:
    """
    GET 订阅 URL，返回完整内容 + 机场取的名字。
    始终直连（空 ProxyHandler）；用 ClashMeta UA 让机场以为我们是合法 Clash 客户端。
    """
    handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(handler)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with opener.open(req, timeout=timeout) as resp:
            content = resp.read()
            disposition = resp.headers.get("Content-Disposition", "")
            return FetchResult(
                success=True,
                content=content,
                upstream_filename=_parse_content_disposition(disposition),
                size=len(content),
                error="",
            )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:200] if hasattr(e, 'read') else ""
        return FetchResult(False, b"", "", 0, f"HTTP {e.code}: {e.reason} - {body}")
    except urllib.error.URLError as e:
        return FetchResult(False, b"", "", 0, f"网络错误: {e.reason}")
    except (OSError, socket.timeout) as e:
        return FetchResult(False, b"", "", 0, f"超时或连接失败: {e}")


# ============================================================
#  本地 HTTP 服务器（用于把内容喂给 subconverter，避开 414 + UA 问题）
# ============================================================

@contextmanager
def serve_content_locally(content: bytes) -> Iterator[str]:
    """
    在 127.0.0.1 随机端口起一个临时 HTTP 服务器，serve `content`。
    yield 出 URL，离开 with 块时自动停服务器。

    解决两个问题：
      1. URL 长度: data: URI 把 KB 级内容塞 URL 会撞 subconverter 的 URL 长度上限 (414)
      2. UA 问题:  传订阅原 URL 给 subconverter，subconverter 用自己的 UA 拉，
                  某些机场拒绝非 Clash UA，返回错误页 → 'No nodes were found'
      本地 HTTP 服务器同时解决两者：URL 短（~30 字节），且我们控制响应内容。
    """
    # 用闭包捕获 content，不污染类属性
    payload = content

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()

        # 静默模式：不要污染 subgen 的输出
        def log_message(self, format, *args):
            pass

    # bind 到随机端口（port=0 让 OS 自动选）
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/sub"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
    target: str = "clash",
) -> tuple[FetchResult, ConvertResult, str]:
    """
    完整流程:
      1. subgen 用 ClashMeta UA 拉订阅完整内容（直连，不读 HTTP_PROXY）
      2. 在本地 127.0.0.1:RANDOM 起临时 HTTP 服务器 serve 这份内容
      3. 把本地服务器 URL 传给 subconverter
      4. subconverter 从本地 socket 拉，处理，返回 YAML

    返回 (fetch_result, convert_result, final_filename)

    final_filename 优先级:
      1. HTTP Content-Disposition 头里的 filename（机场自己取的原名）
      2. URL hostname 推导（兜底）
      然后 + [CONV] 前缀
    """
    # 1. 拉订阅完整内容（subgen 用 ClashMeta UA，不读 HTTP_PROXY）
    fetch = fetch_subscription(subscription_url)

    # 2. 决定最终 filename
    if fetch.success and fetch.upstream_filename:
        original_name = fetch.upstream_filename
    else:
        original_name = derive_name_from_url(subscription_url)
    final_filename = make_filename(original_name)

    # 3. 拉取失败 → 直接返回
    if not fetch.success:
        return (
            fetch,
            ConvertResult(False, "", "", 0, 0, 0, f"订阅拉取失败: {fetch.error}"),
            final_filename,
        )

    # 4. 起本地临时 HTTP 服务器，喂内容给 subconverter
    with serve_content_locally(fetch.content) as local_url:
        convert_url = build_convert_url(
            local_url,
            target=target,
            config_url=config_url,
            filename=final_filename,
        )
        result = call_subconverter(convert_url)

    return fetch, result, final_filename
