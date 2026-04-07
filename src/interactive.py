"""
交互式向导：纯 input() + 数字选择，无任何 TUI 库
流程：URL → 网络状态信息 → 规则套餐 → 目标客户端 → 确认 → 生成
"""
from __future__ import annotations
from typing import Callable

from env import C
from storage import load_config
from network import detect_env, render_snapshot, get_proxy_setup_notes
from presets_data import PRESETS, find_preset
import subconv


# =================================================================
#  通用 input 助手
# =================================================================

def prompt_text(label: str, default: str = "", validator: Callable[[str], bool] | None = None,
                error_msg: str = "输入无效") -> str:
    """读一个字符串。回车走默认。"""
    while True:
        try:
            shown_default = f" {C.dim('[' + default + ']')}" if default else ""
            raw = input(f"{label}{shown_default}: ").strip()
        except EOFError:
            print()
            raise SystemExit(130)
        except KeyboardInterrupt:
            print(C.dim("\n[已取消]"))
            raise SystemExit(130)

        value = raw if raw else default
        if validator and value and not validator(value):
            print(C.fail(f"  {error_msg}"))
            continue
        return value


def prompt_choice(
    label: str,
    options: list[tuple[str, str]],   # [(value, display), ...]
    default_idx: int = 0,
) -> str:
    """显示编号菜单，让用户输入数字选择。返回选中的 value。"""
    print()
    for i, (_, display) in enumerate(options, 1):
        prefix = "  "
        if i - 1 == default_idx:
            prefix = f"  {C.GREEN}▸{C.RESET} "
        print(f"{prefix}{i}) {display}")

    print()
    while True:
        try:
            raw = input(f"{label} {C.dim(f'[默认 {default_idx + 1}]')}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(C.dim("\n[已取消]"))
            raise SystemExit(130)

        if not raw:
            return options[default_idx][0]
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(options):
                return options[n - 1][0]
        print(C.fail(f"  请输入 1-{len(options)} 之间的数字"))


def prompt_yesno(label: str, default: bool = True) -> bool:
    """y/n 确认。"""
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            raw = input(f"{label} {suffix}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(C.dim("\n[已取消]"))
            raise SystemExit(130)
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print(C.fail("  请输入 y 或 n"))


def prompt_continue(label: str = "按回车继续...") -> None:
    """等用户回车。没有选择，不返回值。"""
    try:
        input(f"  {C.dim(label)}")
    except EOFError:
        print()
        raise SystemExit(130)
    except KeyboardInterrupt:
        print(C.dim("\n[已取消]"))
        raise SystemExit(130)


# =================================================================
#  各步骤
# =================================================================

def step_url() -> str:
    print()
    print(C.bold("[1/4] 订阅 URL"))
    print()
    return prompt_text(
        "  请粘贴订阅链接",
        default="",
        validator=lambda s: s.startswith(("http://", "https://")),
        error_msg="必须以 http:// 或 https:// 开头",
    )


def step_network_info() -> None:
    """仅展示网络状态 + 教学提示，不做任何选择"""
    print()
    print(C.bold("[2/4] 当前网络状态"))
    print()
    print(C.dim("  正在检测..."))
    snap = detect_env()
    print()
    print(render_snapshot(snap))
    print()
    print(C.bold("  ── 提示 ──"))
    for note in get_proxy_setup_notes():
        print(f"  {note}")
    print()
    prompt_continue()


def step_fetch_subscription(url: str) -> "subconv.FetchResult":
    """
    本步骤紧跟网络检测：在用户已经看过当前网络状态的语境下，立即拉订阅。
    失败时进入 r/q 循环，让用户切换网络后重试或退出。

    为什么单独成步：拉订阅和拉 ini 可能要走不同的网络
    （比如订阅域名要国内 IP，ini 走 CDN 直连），分两次让用户有机会切网络。
    """
    print()
    print(C.bold("  ── 准备拉取订阅 ──"))
    print(C.dim("  接下来 subgen 会用 ClashMeta UA 直连拉取订阅 URL。"))
    print(C.dim("  · 如果你的订阅要求特定地区 IP（国内机场常见），"))
    print(C.dim("    请先在 Clash Party 里切到对应地区节点 / 启用 TUN"))
    print(C.dim("  · 如果订阅需要直连出国，请关掉 TUN / 系统代理"))
    print(C.dim("  · 拉订阅和拉 ini 是两次独立请求，可分别切换网络"))
    print()
    prompt_continue("调好网络后按回车开始拉订阅...")

    while True:
        print(C.info("  拉订阅..."))
        fetch_result = subconv.fetch_subscription(url)
        if fetch_result.success:
            print(C.ok(f"  成功 ({fetch_result.size} bytes)"))
            if fetch_result.upstream_filename:
                print(C.dim(f"  机场原名: {fetch_result.upstream_filename}"))
            return fetch_result

        print(C.fail(f"  失败: {fetch_result.error}"))
        print()
        print(C.dim("  常见原因:"))
        print(C.dim("    · 订阅域名被墙 / 当前节点被机场封锁"))
        print(C.dim("    · 切换 Clash Party 的 TUN / 节点后再重试"))
        print()
        try:
            choice = input("  选择 [r=重试 / q=退出]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(130)
        if choice in ("", "r", "retry"):
            print(C.info("  重试..."))
            continue
        if choice in ("q", "quit", "exit"):
            print(C.dim("  已取消"))
            raise SystemExit(130)
        print(C.fail("  无效输入，请输 r / q"))


def step_preset(default_id: str = "Full") -> tuple[str, str]:
    """规则套餐选择。返回 (preset_id, ini_url)"""
    print()
    print(C.bold("[3/4] 规则套餐"))
    print(C.dim("  每个套餐 = 一套「策略组 + 规则」组合，决定 Clash 里能看到哪些分组"))

    options: list[tuple[str, str]] = []
    default_idx = 0
    for i, p in enumerate(PRESETS):
        marker = " ⭐" if p.recommended else "  "
        rules_info = f"~{p.rules_estimate}规则" if p.rules_estimate else ""
        groups_count = f"{len(p.groups)}组" if p.groups else ""
        meta = " · ".join(filter(None, [groups_count, rules_info]))
        meta_str = f" {C.dim('(' + meta + ')')}" if meta else ""
        display = f"{p.name}{marker}{meta_str}"
        options.append((p.id, display))
        if p.id == default_id:
            default_idx = i

    preset_id = prompt_choice("  选择规则套餐", options, default_idx=default_idx)
    preset = find_preset(preset_id)
    assert preset is not None

    # 不再展示该套餐的策略组明细 —— 真实的策略组以 ini 文件为准，
    # 等下一步预检 ini 拉到后由 subconverter 决定，预先展示反而可能不一致。
    print()
    print(C.bold(f"  ── {preset.name} ──"))
    if preset.notes:
        print(f"  {C.dim('说明:')}")
        for n in preset.notes:
            print(f"    · {n}")
    print()

    ini_url = preset.ini_url
    if preset.id == "Custom":
        ini_url = prompt_text(
            "  请输入 ini URL",
            default="https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/config/ACL4SSR_Online_Full.ini",
            validator=lambda s: s.startswith(("http://", "https://")),
            error_msg="必须以 http:// 或 https:// 开头",
        )

    return preset_id, ini_url


def step_target(default: str = "clash") -> str:
    """目标客户端菜单，返回 subconverter 的 target 字符串

    注意：subconverter 没有 'clashmeta' 这个 target，Clash / Clash.Meta / Mihomo /
    Clash Party 都共用 'clash' target 输出的 YAML（格式兼容）
    """
    print()
    print(C.bold("[4/4] 目标客户端"))
    options = [
        ("clash", "Clash 系（Clash / Clash.Meta / Mihomo / Clash Party / Mihomo Party）⭐"),
        ("surge", "Surge"),
        ("quanx", "Quantumult X"),
        ("loon",  "Loon"),
    ]
    default_idx = 0  # clash
    for i, (val, _) in enumerate(options):
        if val == default:
            default_idx = i
            break
    return prompt_choice("  选择目标客户端", options, default_idx=default_idx)


# =================================================================
#  确认页 + 生成
# =================================================================

def show_confirm(url: str, preset_id: str, target: str) -> bool:
    """确认页。只展示 URL / 套餐 / 目标客户端，不预测命名（命名拉取后才知道）"""
    preset = find_preset(preset_id)

    print()
    print(C.bold("=== 请确认 ==="))
    print(f"  订阅 URL    : {url[:60]}{'...' if len(url) > 60 else ''}")
    print(f"  规则套餐    : {preset.name if preset else preset_id}")
    print(f"  目标客户端  : {target}")
    print(C.bold("============="))
    print()
    return prompt_yesno("  确认生成转换 URL？", default=True)


def step_check_ini(ini_url: str) -> str:
    """
    本步骤紧跟套餐选择：用户刚选完规则套餐，立刻预检 ini URL 可达性。
    与拉订阅分开是因为两者可能需要不同的网络（订阅常要国内 IP，
    ini 走 jsdelivr CDN 通常直连即可）。
    返回 effective_ini_url，"" 表示用 subconverter 内置 fallback。
    """
    if not ini_url:
        print()
        print(C.dim("  (无 ini URL，使用 subconverter 内置默认 13 组)"))
        return ""

    print()
    print(C.bold("  ── 准备拉取规则配置 ini ──"))
    print(C.dim("  即将预检以下 ini URL 是否可达："))
    print(C.dim(f"    {ini_url}"))
    print(C.dim("  · 此 URL 走 jsdelivr CDN，国内多数情况直连可达"))
    print(C.dim("  · 如果刚才为了拉订阅改了网络，现在可视情况切回直连"))
    print(C.dim("  · 拉不到 ini 时可选 fallback（subconverter 内置 13 组）"))
    print()
    prompt_continue("调好网络后按回车开始预检 ini...")

    return _check_ini_with_retry(ini_url)


def _check_ini_with_retry(ini_url: str) -> str:
    """
    预检 ini 可达性，失败时进入 r/f/q 循环。
    返回:
      - ini_url     表示用户最终选择继续用这个 ini（重试成功）
      - ""          表示 fallback (用 subconverter 内置默认 13 组)
    抛出 SystemExit 表示用户选择退出
    """
    while True:
        ok, err = subconv.check_ini_reachable(ini_url)
        if ok:
            print(C.ok(f"  ini 可达 ✓"))
            return ini_url
        # 不可达 → 走交互循环
        print(C.fail(f"  ini 拉取失败: {err}"))
        print()
        print(C.bold("  ── 怎么办？──"))
        print(C.dim("    URL: " + ini_url))
        print()
        print(C.dim("  原因通常是国内防火墙或节点阻断了 jsdelivr / GitHub raw 域名"))
        print(C.dim("  解决方法："))
        print(C.dim("    a. 启用 Clash Party 的 TUN 模式 / 系统代理后，按 r 重试"))
        print(C.dim("    b. 或用 subconverter 内置默认配置（仅 13 组，功能简化）"))
        print()
        try:
            choice = input("  选择 [r=重试 / f=用内置默认 fallback / q=退出]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(130)

        if choice in ("", "r", "retry"):
            print(C.info("  重试..."))
            continue
        if choice in ("f", "fallback"):
            print(C.warn("  使用 subconverter 内置默认 (13 组)"))
            return ""
        if choice in ("q", "quit", "exit"):
            print(C.dim("  已取消"))
            raise SystemExit(130)
        print(C.fail("  无效输入，请输 r / f / q"))


def do_generate(
    url: str,
    preset_id: str,
    target: str,
    fetch_result: "subconv.FetchResult",
    effective_ini_url: str,
    final_filename: str,
) -> int:
    """
    执行转换，返回 exit code。

    订阅内容和 ini 可达性都已经在向导阶段拉好/检过了
    （订阅在网络步骤后立刻拉，ini 在选完套餐后立刻检），
    本函数只负责：起本地 HTTP 服务器 + 调 subconverter + 等用户按回车。

    关键时序（解决「Clash 导入时 127.0.0.1 拒绝连接」问题）：
      1. 起本地 HTTP 服务器（with 块开始，喂之前已拉好的订阅 content）
      2. 调 subconverter 完成转换 + 打印 URL
      3. 等用户回车 ←── 本地 HTTP 服务器和 subconverter 在此期间都活着
      4. with 块退出，本地 HTTP 服务器关闭
      5. cli.py 主流程退出，subconverter 被杀
    """
    preset = find_preset(preset_id)
    if preset is None:
        print(C.fail(f"未知的预设 ID: {preset_id}"))
        return 1

    print()
    print(C.info("调用本地 subconverter 转换..."))

    # 关键：本地 HTTP 服务器必须在 with 块内一直存活，
    # 直到用户按回车（=Clash 已拉完订阅）才关闭
    with subconv.serve_content_locally(fetch_result.content) as local_url:
        convert_url = subconv.build_convert_url(
            local_url,
            target=target,
            config_url=effective_ini_url,  # 可能是空字符串（fallback 模式）
            filename=final_filename,
        )
        convert_result = subconv.call_subconverter(convert_url)

        if not convert_result.success:
            print(C.fail(f"  转换失败: {convert_result.error}"))
            return 3

        print(C.ok("  转换成功"))
        print(f"    节点数:    {convert_result.proxy_count}")
        print(f"    策略组:    {convert_result.group_count}")
        print(f"    规则数:    {convert_result.rule_count}")
        print(f"    YAML 大小: {len(convert_result.yaml_content)} bytes")
        print(f"    导入后名:  {C.CYAN}{final_filename}{C.RESET}")
        print()
        print(C.bold("📋 转换 URL（粘贴到 Clash Party 订阅）:"))
        print()
        print(convert_result.url)
        print()
        print(C.bold(C.YELLOW + "⚠ 重要：在你按回车之前，"
                              "subconverter 和本地数据服务器都会保持运行" + C.RESET))
        print(C.dim("  操作步骤:"))
        print(C.dim("    1. 复制上面的 URL"))
        print(C.dim("    2. 粘贴到 Clash Party 的「添加订阅」"))
        print(C.dim("    3. 等 Clash Party 显示『订阅已添加 / 节点已加载』"))
        print(C.dim("    4. 回到这里按回车退出 subgen"))
        print(C.dim("  如果太早按回车，subconverter 和本地服务器会被关掉，订阅 URL 立刻失效"))
        print()
        try:
            input("  导入完成？按回车退出 subgen: ")
        except (EOFError, KeyboardInterrupt):
            print()
    # ── with 块结束，本地 HTTP 服务器在这里关闭 ──
    print()
    return 0


# =================================================================
#  入口
# =================================================================

def run_wizard(initial_url: str = "") -> int:
    """跑完整向导，返回 exit code。不读 state，从 config 取默认值。"""
    cfg = load_config()
    default_preset = cfg.get("general", {}).get("default_preset_id", "Full")
    default_target = cfg.get("general", {}).get("default_target", "clashmeta")

    print()
    print(C.bold("======================================="))
    print(C.bold("  subgen v0.2 · 订阅转换工具"))
    print(C.bold("======================================="))
    print()
    print(C.dim("  操作提示:"))
    print(C.dim("    · 菜单选择: 输入数字 + 回车"))
    print(C.dim("    · 走默认值: 直接按回车（标 ▸ 的那项）"))
    print(C.dim("    · 取消退出: Ctrl+C"))
    print(C.dim("  本工具会分两次拉网络资源（订阅 / ini），可分别切换网络"))

    # ── [1/4] URL ──
    url = initial_url or step_url()

    # ── [2/4] 网络状态 → 立即拉订阅（紧跟网络检测，方便用户先调好网络）──
    step_network_info()
    fetch_result = step_fetch_subscription(url)
    final_filename = subconv.compute_filename(fetch_result, url)

    # ── [3/4] 套餐选择 → 立即预检 ini（订阅和 ini 可能要不同网络）──
    preset_id, ini_url = step_preset(default_id=default_preset)
    effective_ini_url = step_check_ini(ini_url)

    # ── [4/4] 目标客户端 ──
    target = step_target(default=default_target)

    if not show_confirm(url, preset_id, target):
        print(C.warn("已取消"))
        return 130

    return do_generate(url, preset_id, target, fetch_result, effective_ini_url, final_filename)
