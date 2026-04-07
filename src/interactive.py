"""
交互式向导：纯 input() + 数字选择，无任何 TUI 库
流程：URL → 网络模式（带检测） → 规则套餐 → 客户端 → 确认 → 生成
"""
from __future__ import annotations
import sys
from typing import Callable

from env import C
from storage import load_state, save_state
from network import detect_env, render_snapshot, suggest_mode, get_mode_notes
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


# =================================================================
#  各步骤
# =================================================================

def step_url(default: str = "") -> str:
    print()
    print(C.bold("[1/4] 订阅 URL"))
    print()
    return prompt_text(
        "  请粘贴订阅链接",
        default=default,
        validator=lambda s: s.startswith(("http://", "https://")),
        error_msg="必须以 http:// 或 https:// 开头",
    )


def step_network(default_mode: str = "DIRECT") -> tuple[str, str]:
    """
    网络模式选择。
    返回 (mode, custom_proxy_url)
    """
    print()
    print(C.bold("[2/4] 网络模式"))
    print()
    print(C.dim("  正在检测当前网络环境..."))

    snap = detect_env(probe_proxy=False)
    print()
    print(render_snapshot(snap))
    print()

    suggested_mode, suggested_reason = suggest_mode(snap)
    print(C.info(f"建议: {C.bold(suggested_mode)} - {suggested_reason}"))
    print()

    options = [
        ("DIRECT", "直连 (DIRECT) - 用本机直接拉，不走任何代理"),
        ("PROXY",  "走代理 (PROXY) - http://127.0.0.1:7890 (Clash Party 默认端口)"),
        ("CUSTOM", "自定义代理 URL"),
    ]
    default_idx = 0
    for i, (val, _) in enumerate(options):
        if val == suggested_mode:
            default_idx = i
            break

    mode = prompt_choice("  选择拉取此订阅使用的网络", options, default_idx=default_idx)

    # 显示该模式的注意事项
    print()
    print(C.bold("  ── 注意事项 ──"))
    notes = get_mode_notes(mode, snap)
    for note in notes:
        print(f"  {note}")
    print()

    custom = ""
    if mode == "CUSTOM":
        custom = prompt_text(
            "  自定义代理 URL",
            default="http://127.0.0.1:7890",
            validator=lambda s: s.startswith(("http://", "https://", "socks5://", "socks5h://")),
            error_msg="必须以 http:// / https:// / socks5:// 开头",
        )

    if not prompt_yesno("  确认使用此网络模式继续吗？", default=True):
        print(C.warn("  → 重新选择网络模式"))
        return step_network(default_mode)

    return mode, custom


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

    # 显示该套餐的策略组明细
    print()
    print(C.bold(f"  ── {preset.name} ──"))
    if preset.groups:
        print(f"  {C.dim('策略组 (' + str(len(preset.groups)) + ' 个):')}")
        for i in range(0, len(preset.groups), 4):
            chunk = preset.groups[i:i + 4]
            print("    " + "  ".join(g.ljust(14) for g in chunk))
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
    print()
    print(C.bold("[4/4] 目标客户端"))
    options = [
        ("clash",     "Clash / Clash for Windows"),
        ("clashmeta", "Clash.Meta / Mihomo / Clash Party / Mihomo Party"),
        ("surge",     "Surge"),
        ("quanx",     "Quantumult X"),
        ("loon",      "Loon"),
        ("singbox",   "sing-box"),
    ]
    default_idx = 0
    for i, (val, _) in enumerate(options):
        if val == default:
            default_idx = i
            break
    return prompt_choice("  选择目标客户端", options, default_idx=default_idx)


# =================================================================
#  确认页 + 生成
# =================================================================

def show_confirm(url: str, mode: str, custom_proxy: str, preset_id: str, target: str) -> bool:
    preset = find_preset(preset_id)
    derived_name = subconv.derive_name_from_url(url)
    final_filename = subconv.make_filename(derived_name)

    print()
    print(C.bold("═══════════════ 请确认 ═══════════════"))
    print(f"  订阅 URL    : {url[:60]}{'...' if len(url) > 60 else ''}")
    if mode == "CUSTOM":
        print(f"  网络模式    : 自定义代理 ({custom_proxy})")
    else:
        print(f"  网络模式    : {mode}")
    print(f"  规则套餐    : {preset.name if preset else preset_id}")
    print(f"  目标客户端  : {target}")
    print(f"  导入后命名  : {C.CYAN}{final_filename}{C.RESET}  {C.dim('← Clash 导入时显示的配置名')}")
    print(C.bold("═══════════════════════════════════════"))
    print()
    return prompt_yesno("  确认生成转换 URL？", default=True)


def do_generate(url: str, mode: str, custom_proxy: str, preset_id: str, target: str) -> int:
    """执行生成。返回 exit code。"""
    preset = find_preset(preset_id)
    if preset is None:
        print(C.fail(f"未知的预设 ID: {preset_id}"))
        return 1

    print()
    print(C.info(f"步骤 1/2: 用 {C.bold(mode)} 模式拉取订阅..."))
    fetch_result, convert_result, final_filename = subconv.generate(
        subscription_url=url,
        network_mode=mode,
        custom_proxy=custom_proxy,
        config_url=preset.ini_url,
        target=target,
    )

    if not fetch_result.success:
        print(C.fail(f"  拉取失败: {fetch_result.error}"))
        return 2

    print(C.ok(f"  拉取成功 ({fetch_result.size} bytes)"))
    print()
    print(C.info("步骤 2/2: 调本地 subconverter 转换..."))

    if not convert_result.success:
        print(C.fail(f"  转换失败: {convert_result.error}"))
        return 3

    print(C.ok(f"  转换成功"))
    print(f"    节点数:   {convert_result.proxy_count}")
    print(f"    策略组:   {convert_result.group_count}")
    print(f"    规则数:   {convert_result.rule_count}")
    print(f"    YAML 大小: {len(convert_result.yaml_content)} bytes")
    print()
    print(C.bold("📋 转换 URL（粘贴到 Clash Party 订阅）:"))
    print()
    print(convert_result.url)
    print()
    print(C.bold(f"📛 Clash 导入后的配置名: {C.CYAN}{final_filename}{C.RESET}"))
    print(C.dim("    （subconverter 通过 Content-Disposition 告知客户端，"))
    print(C.dim("     Clash for Windows / Mihomo Party 等会自动用作默认名）"))
    print()
    print(C.dim("提示: 这是一次性快照 URL，订阅自动更新会失效。"))
    print(C.dim("      节点变化后，重新跑 ./subgen 生成新的 URL。"))
    print()
    return 0


# =================================================================
#  入口
# =================================================================

def run_wizard(initial_url: str = "") -> int:
    """跑完整向导，返回 exit code"""
    state = load_state()
    last = state.get("last", {})

    print()
    print(C.bold("═══════════════════════════════════════"))
    print(C.bold("  subgen v0.1 · 订阅转换工具"))
    print(C.bold("═══════════════════════════════════════"))

    # Step 1: URL
    url = initial_url or step_url(default=last.get("subscription_url", ""))

    # Step 2: 网络模式
    mode, custom = step_network(default_mode=last.get("network_mode", "DIRECT"))

    # Step 3: 规则套餐
    preset_id, ini_url = step_preset(default_id=last.get("preset_id", "Full"))

    # Step 4: 目标客户端
    target = step_target(default=last.get("target", "clash"))

    # 确认页
    if not show_confirm(url, mode, custom, preset_id, target):
        print(C.warn("已取消"))
        return 130

    # 生成
    rc = do_generate(url, mode, custom, preset_id, target)

    # 保存上次选择
    state["last"] = {
        "subscription_url": url,
        "network_mode": mode,
        "custom_proxy": custom,
        "preset_id": preset_id,
        "target": target,
    }
    save_state(state)

    return rc
