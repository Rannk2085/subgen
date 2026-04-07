"""
ACL4SSR 预设套餐定义
每个套餐 = 一个 ACL4SSR ini 文件 = 一套「策略组 + 规则」组合

ACL4SSR 仓库主页: https://github.com/ACL4SSR/ACL4SSR
ini 文件目录:    https://github.com/ACL4SSR/ACL4SSR/tree/master/Clash/config
"""
from __future__ import annotations
from typing import NamedTuple


class Preset(NamedTuple):
    id: str            # 短 ID（命令行用）
    name: str          # 显示名
    description: str   # 一句话说明
    groups: list[str]  # 策略组列表
    rules_estimate: int  # 估算规则数
    ini_url: str       # 远程 ini 完整 URL
    recommended: bool  # 是否标星
    notes: list[str]   # 适用场景或注意事项


# ACL4SSR 仓库的 raw URL 前缀
_BASE = "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/config"


PRESETS: list[Preset] = [
    Preset(
        id="Full",
        name="ACL4SSR Full 完整版",
        description="19 个策略组，~10000 规则。最全功能，覆盖所有主流分流场景",
        groups=[
            "🚀 节点选择", "♻️ 自动选择",
            "🌍 国外媒体", "🌏 国内媒体", "📲 电报信息",
            "Ⓜ️ 微软Azure", "Ⓜ️ 微软服务", "🍎 苹果服务", "📢 谷歌FCM",
            "🛑 全球拦截", "🍃 应用净化", "🎯 全球直连", "🐟 漏网之鱼",
            "🇭🇰 香港节点", "🇯🇵 日本节点", "🇺🇸 美国节点",
            "🇸🇬 狮城节点", "🇨🇳 台湾节点", "🌍 其它地区",
        ],
        rules_estimate=10000,
        ini_url=f"{_BASE}/ACL4SSR_Online_Full.ini",
        recommended=True,
        notes=[
            "默认推荐，适合 90% 用户",
            "策略组按地区+服务双维度分组",
        ],
    ),

    Preset(
        id="Mini",
        name="ACL4SSR Mini 精简版",
        description="5 个策略组，~4000 规则。极简党首选，启动快",
        groups=[
            "🚀 节点选择", "♻️ 自动选择",
            "🛑 全球拦截", "🎯 全球直连", "🐟 漏网之鱼",
        ],
        rules_estimate=4000,
        ini_url=f"{_BASE}/ACL4SSR_Online_Mini.ini",
        recommended=False,
        notes=[
            "只区分国内/国外，不细分媒体",
            "Clash Party 启动更快、内存占用更少",
        ],
    ),

    Preset(
        id="FullAdblock",
        name="ACL4SSR Full + AdblockPlus",
        description="同 Full（19 组）+ 强力广告拦截规则集",
        groups=[
            "🚀 节点选择", "♻️ 自动选择",
            "🌍 国外媒体", "🌏 国内媒体", "📲 电报信息",
            "Ⓜ️ 微软Azure", "Ⓜ️ 微软服务", "🍎 苹果服务", "📢 谷歌FCM",
            "🛑 全球拦截", "🍃 应用净化", "🎯 全球直连", "🐟 漏网之鱼",
            "🇭🇰 香港节点", "🇯🇵 日本节点", "🇺🇸 美国节点",
            "🇸🇬 狮城节点", "🇨🇳 台湾节点", "🌍 其它地区",
        ],
        rules_estimate=12000,
        ini_url=f"{_BASE}/ACL4SSR_Online_Full_AdblockPlus.ini",
        recommended=False,
        notes=[
            "广告拦截更激进，加入 EasyList + EasyPrivacy",
            "适合重度广告厌恶者",
            "可能误杀部分网站功能",
        ],
    ),

    Preset(
        id="FullNoAuto",
        name="ACL4SSR Full NoAuto 无自动测速",
        description="同 Full，但所有策略组改为手动选择，不自动切换节点",
        groups=[
            "🚀 节点选择",
            "🌍 国外媒体", "🌏 国内媒体", "📲 电报信息",
            "Ⓜ️ 微软Azure", "Ⓜ️ 微软服务", "🍎 苹果服务", "📢 谷歌FCM",
            "🛑 全球拦截", "🍃 应用净化", "🎯 全球直连", "🐟 漏网之鱼",
            "🇭🇰 香港节点", "🇯🇵 日本节点", "🇺🇸 美国节点",
            "🇸🇬 狮城节点", "🇨🇳 台湾节点", "🌍 其它地区",
        ],
        rules_estimate=10000,
        ini_url=f"{_BASE}/ACL4SSR_Online_NoAuto.ini",
        recommended=False,
        notes=[
            "去掉了 ♻️ 自动选择 组",
            "节点切换完全手动，适合追求稳定连接的人",
        ],
    ),

    Preset(
        id="NoApple",
        name="ACL4SSR NoApple 苹果直连",
        description="同 Full，但苹果服务全部直连（去掉 🍎 苹果服务 组）",
        groups=[
            "🚀 节点选择", "♻️ 自动选择",
            "🌍 国外媒体", "🌏 国内媒体", "📲 电报信息",
            "Ⓜ️ 微软Azure", "Ⓜ️ 微软服务", "📢 谷歌FCM",
            "🛑 全球拦截", "🍃 应用净化", "🎯 全球直连", "🐟 漏网之鱼",
            "🇭🇰 香港节点", "🇯🇵 日本节点", "🇺🇸 美国节点",
            "🇸🇬 狮城节点", "🇨🇳 台湾节点", "🌍 其它地区",
        ],
        rules_estimate=9500,
        ini_url=f"{_BASE}/ACL4SSR_Online_NoApple.ini",
        recommended=False,
        notes=[
            "iCloud 同步党、Apple ID 国区用户",
            "避免 Apple 服务被代理污染",
        ],
    ),

    Preset(
        id="NoAutoNoFakeIP",
        name="ACL4SSR NoAuto NoFakeIP",
        description="无自动测速 + 关闭 fake-ip DNS",
        groups=[
            "🚀 节点选择",
            "🌍 国外媒体", "🌏 国内媒体", "📲 电报信息",
            "Ⓜ️ 微软Azure", "Ⓜ️ 微软服务", "🍎 苹果服务", "📢 谷歌FCM",
            "🛑 全球拦截", "🍃 应用净化", "🎯 全球直连", "🐟 漏网之鱼",
            "🇭🇰 香港节点", "🇯🇵 日本节点", "🇺🇸 美国节点",
            "🇸🇬 狮城节点", "🇨🇳 台湾节点", "🌍 其它地区",
        ],
        rules_estimate=10000,
        ini_url=f"{_BASE}/ACL4SSR_Online_NoAuto_NoFakeIP.ini",
        recommended=False,
        notes=[
            "适合需要真实 DNS 的特殊网络环境",
            "如：透明代理、容器网络、某些 IPv6-only",
        ],
    ),

    Preset(
        id="MiniFallback",
        name="ACL4SSR Mini Fallback",
        description="同 Mini（5 组），但节点用 fallback 模式",
        groups=[
            "🚀 节点选择", "♻️ 故障转移",
            "🛑 全球拦截", "🎯 全球直连", "🐟 漏网之鱼",
        ],
        rules_estimate=4000,
        ini_url=f"{_BASE}/ACL4SSR_Online_Mini_Fallback.ini",
        recommended=False,
        notes=[
            "fallback：前一个节点挂了自动切下一个",
            "和 url-test（按延迟自动选）的区别",
        ],
    ),

    Preset(
        id="WithGFW",
        name="ACL4SSR Online + GFW List",
        description="基础组合 + GFW List（精确黑名单）",
        groups=[
            "🚀 节点选择", "♻️ 自动选择",
            "🌍 国外媒体", "🛑 全球拦截",
            "🎯 全球直连", "🐟 漏网之鱼",
        ],
        rules_estimate=8000,
        ini_url=f"{_BASE}/ACL4SSR_Online_WithGFW.ini",
        recommended=False,
        notes=[
            "采用 GFW List 精确黑名单方式",
            "适合喜欢「黑名单代理」逻辑的用户",
        ],
    ),

    # 第 9 个：自定义入口
    Preset(
        id="Custom",
        name="自定义 ini URL",
        description="手动输入任意 ACL4SSR 兼容的 ini 链接",
        groups=[],
        rules_estimate=0,
        ini_url="",  # 运行时由用户输入
        recommended=False,
        notes=[
            "支持其他规则提供者：lhie1 / ConnersHua / Loyalsoldier 等",
            "ini 必须符合 subconverter 的格式",
        ],
    ),
]


def find_preset(preset_id: str) -> Preset | None:
    """按 ID 查找预设"""
    for p in PRESETS:
        if p.id == preset_id:
            return p
    return None


def get_default_preset() -> Preset:
    """返回标记为推荐的预设"""
    for p in PRESETS:
        if p.recommended:
            return p
    return PRESETS[0]
