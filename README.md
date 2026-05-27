# subgen

> Portable, folder-based interactive wrapper for [subconverter](https://github.com/MetaCubeX/subconverter).
> Clone-and-run. No installation, no system services, no domestic mirrors, no background daemons.
>
> [简体中文](#中文说明)

---

## What is this

`subgen` is a small CLI tool that wraps a local `subconverter` HTTP service to:

- Fetch your airport (机场) subscription directly
- Convert it into a Clash / Clash.Meta YAML using preset rule packages (ACL4SSR variants)
- Tag the converted profile with a `[CONV]` prefix and `.yaml` suffix so you can tell at a glance which profile in your Clash client came from subgen vs. the original subscription

Everything lives inside the cloned folder. Nothing is written to `~/.config/`, `~/.local/`, `%APPDATA%`, or any system-wide path.

`subconverter` runs in **ephemeral mode**: subgen spawns it as a child process only for the duration of a single command, then stops it automatically on exit. There is no background daemon and no PID file to manage.

## Quick start

### Linux / macOS

```bash
git clone https://github.com/Rannk2085/subgen.git
cd subgen
./subgen install   # first time only: download subconverter binary
./subgen           # launch the interactive wizard
```

### Windows

```cmd
git clone https://github.com/Rannk2085/subgen.git
cd subgen
subgen.bat install
subgen.bat
```

## Requirements

- **Python 3.11+** (uses stdlib `tomllib`, no third-party packages)
- Linux / macOS / Windows
- `git` (for cloning and updating via `git pull`)

If `python3` isn't installed:

- Ubuntu/Debian: `sudo apt install python3`
- Windows: `winget install Python.Python.3.12`
- macOS: `brew install python3`

## Commands

```
./subgen                       # Interactive wizard (most common)
./subgen gen <URL>             # CLI mode, skip the URL prompt
./subgen install               # Download subconverter (first run)
./subgen install --force       # Force reinstall
./subgen clean                 # Clear data/cache and data/logs
./subgen doctor                # Diagnose environment
./subgen version               # Print version
./subgen help                  # Show help
```

> Note: there is **no** `status` / `start` / `stop` / `restart` command. subgen will spawn `subconverter` when a command needs it and terminate it automatically when the command finishes.

## Networking

subgen always fetches subscriptions **directly**. It does **not** read `HTTP_PROXY` / `HTTPS_PROXY` environment variables at runtime.

If your subscription requires a proxy (e.g. an overseas-only endpoint), use one of:

1. **Clash Party TUN mode** - turn on the virtual NIC in Clash Party so that all TCP traffic on the machine (including subgen's) gets captured and routed through Clash.
2. **proxychains4** - wrap the launcher:

   ```bash
   proxychains4 ./subgen
   ```

If the subscription endpoint requires a specific region IP, switch to a node of the corresponding region in Clash Party **before** running subgen.

> `./subgen install` is the one exception: when downloading the `subconverter` binary from GitHub, it can honor `HTTPS_PROXY`. It first checks whether GitHub is already reachable on the current network (including TUN/system proxy scenarios), and only suggests setting `HTTPS_PROXY` if GitHub is unreachable. Runtime subscription fetches are always direct.

## The 4-step wizard

When you run `./subgen` you get:

```
[1/4] Subscription URL
[2/4] Current network status   (informational only, no choice to make)
[3/4] Rule preset              (default: Full, press Enter to accept)
[4/4] Target client            (default: clashmeta, press Enter to accept)
       ↓
       Confirm → Generate
```

Step 2 just shows you what subgen sees about the current network (direct reachability, detected egress, etc.). There is no mode picker - subgen always goes direct, so your job is to make the network itself right (via Clash TUN / proxychains / region switch).

## Rule presets

Step 3 picks an ACL4SSR variant. Each variant defines a different set of proxy groups + rules in the generated YAML.

| ID | 中文名 | Groups | Rules |
|---|---|---|---|
| `full` ⭐ | 完整版 | 19 | ~10000 |
| `mini` | 精简版 | 5 | ~4000 |
| `full_adblock` | 完整版 + 去广告 | 19 | ~12000 |
| `full_noauto` | 完整版无自动测速 | 18 | ~10000 |
| `noapple` | 无 Apple 分流 | 18 | ~9500 |
| `noauto_nofakeip` | 无自动测速无 FakeIP | 18 | ~10000 |
| `mini_fallback` | 精简版 Fallback | 5 | ~4000 |
| `withgfw` | GFW List | 6 | ~8000 |

Press Enter on step 3 to accept `full`.

## Naming convention

Every Clash config produced by subgen gets a `[CONV]` prefix and `.yaml` suffix when imported into your Clash client:

```
Original subscription:  https://link01.nobodys.uk/api/v1/...
Imported profile name:  [CONV] link01.yaml
```

This lets you distinguish **"raw subscription"** from **"subgen-converted"** in one glance.

Implementation detail: the name is set via subconverter's `&filename=` parameter, which subconverter writes into the HTTP `Content-Disposition` response header. subgen does **not** modify any node's `name:` field - individual proxy node names are preserved exactly as they come from the upstream subscription.

The `[CONV]` prefix and `.yaml` suffix are hardcoded and not configurable.

## Folder layout

```
subgen/                          ← git clone root
├── README.md
├── LICENSE
├── .gitignore
├── subgen                       ← Linux / macOS launcher (bash)
├── subgen.bat                   ← Windows launcher
├── src/                         ← Python source (committed)
│   ├── main.py
│   ├── cli.py
│   ├── interactive.py
│   ├── env.py
│   ├── storage.py
│   ├── network.py
│   ├── subconv.py
│   ├── process.py
│   ├── downloader.py
│   └── presets_data.py
└── data/                        ← runtime data (gitignored)
    ├── bin/subconverter/        ← downloaded binary
    ├── config.toml              ← global config
    ├── presets/                 ← named presets (TOML)
    ├── cache/                   ← remote resource cache
    └── logs/                    ← subconverter + subgen logs
```

Things **not** in this tree (by design):

- **No `data/state.toml`** - subgen does not remember the last run's choices.
- **No `data/run/`** - no PID file, because subconverter is ephemeral.

## Updating

```bash
cd subgen
git pull
```

That's the whole update mechanism. There is no `self-update` command.

To refresh the bundled `subconverter` binary:

```bash
./subgen install --force
```

ACL4SSR rules are fetched fresh on every conversion by `subconverter` itself, so they are always up to date.

## Troubleshooting

Run the built-in diagnostic:

```bash
./subgen doctor
```

It checks Python version, data directory, subconverter binary, and basic network reachability.

To wipe caches and logs:

```bash
./subgen clean
```

## License

MIT. See [LICENSE](LICENSE).

---

# 中文说明

## 这是什么

`subgen` 是一个**纯文件夹形态、零安装、零系统侵入**的 [subconverter](https://github.com/MetaCubeX/subconverter) 交互式包装工具。

核心功能：

1. 直连拉取机场订阅
2. 调本地 `subconverter` 套用 ACL4SSR 规则包转换成 Clash / Clash.Meta 配置
3. 自动给转换后的配置加 `[CONV]` 前缀和 `.yaml` 后缀，让你在 Clash 客户端里一眼区分「原始订阅」vs「subgen 转换的」

所有数据（配置、缓存、日志、subconverter 二进制）都在 clone 出来的文件夹里，**完全不写系统目录**。

`subconverter` 用 **ephemeral（短生命周期）** 模式跑：subgen 启动时拉起子进程，命令结束后自动停掉。没有后台常驻进程，也没有 PID 文件。

## 快速上手

### Linux / macOS

```bash
git clone https://github.com/Rannk2085/subgen.git
cd subgen
./subgen install   # 首次：下载 subconverter 二进制
./subgen           # 进入交互式向导
```

### Windows

```cmd
git clone https://github.com/Rannk2085/subgen.git
cd subgen
subgen.bat install
subgen.bat
```

## 系统要求

- **Python 3.11+**（用了内置 `tomllib`，无任何第三方依赖）
- Linux / macOS / Windows 都行
- `git`（用于 clone 和更新 `git pull`）

## 命令

```
./subgen                       交互式向导（最常用）
./subgen gen <URL>             命令行模式，跳过 URL 输入
./subgen install               下载 subconverter 二进制（首次使用）
./subgen install --force       强制重装
./subgen clean                 清空 cache 和 logs
./subgen doctor                诊断当前环境
./subgen version               显示版本
./subgen help                  显示帮助
```

> 注意：**没有** `status` / `start` / `stop` / `restart`。subgen 跑命令时自动拉起 `subconverter`，命令结束后自动停掉，用户不需要手动管理。

## 网络策略

subgen **始终直连**拉订阅，**不读** `HTTP_PROXY` / `HTTPS_PROXY` 环境变量。

如需走代理，二选一：

1. **Clash Party TUN 模式**：在 Clash Party 里启用 TUN（虚拟网卡），整机的 TCP 流量（包括 subgen）都会被 Clash Party 接管。
2. **proxychains4**：用 proxychains 包装启动

   ```bash
   proxychains4 ./subgen
   ```

如果订阅域名要求特定地区 IP，**先**在 Clash Party 切对应地区节点，再跑 subgen。

> 例外：`./subgen install` 下载 subconverter 时可以读 `HTTPS_PROXY`。它会先检测当前网络是否可达 GitHub（含 TUN/系统代理场景），只有不可达时才提示你设置 `HTTPS_PROXY`。运行时拉订阅永远直连。

## 4 步向导

跑 `./subgen` 会得到：

```
[1/4] 订阅 URL
[2/4] 当前网络状态   （只是信息展示，无需选择）
[3/4] 规则套餐       （默认 Full，回车直接走默认）
[4/4] 目标客户端     （默认 clashmeta，回车直接走默认）
       ↓
       确认 → 生成
```

第 2 步只是展示当前网络情况（直连可达性、出口等），没有模式选择——subgen 固定直连，网络本身的问题请用 Clash TUN / proxychains / 切地区节点解决。

## 8 个 ACL4SSR 套餐

第 3 步选 ACL4SSR 变体，每个变体定义一套不同的策略组 + 规则。

| ID | 中文名 | 策略组数 | 规则数 |
|---|---|---|---|
| `full` ⭐ | 完整版 | 19 | ~10000 |
| `mini` | 精简版 | 5 | ~4000 |
| `full_adblock` | 完整版 + 去广告 | 19 | ~12000 |
| `full_noauto` | 完整版无自动测速 | 18 | ~10000 |
| `noapple` | 无 Apple 分流 | 18 | ~9500 |
| `noauto_nofakeip` | 无自动测速无 FakeIP | 18 | ~10000 |
| `mini_fallback` | 精简版 Fallback | 5 | ~4000 |
| `withgfw` | GFW List | 6 | ~8000 |

第 3 步直接回车 = 选 `full`。

## 命名约定

每次 subgen 转换出来的 Clash 配置导入到客户端时，名称会自动加 `[CONV]` 前缀和 `.yaml` 后缀：

```
原始订阅:   https://link01.nobodys.uk/api/v1/...
导入后名称: [CONV] link01.yaml
```

这样可以一眼区分「原始订阅」vs「subgen 转换过的」。

实现方式：通过 subconverter 的 `&filename=` 参数，让 subconverter 把它写进 HTTP 响应头 `Content-Disposition`。subgen **不修改任何节点的 `name:` 字段**，节点名保持原样。

`[CONV]` 前缀和 `.yaml` 后缀是硬编码的，不可配置。

## 目录结构

```
subgen/                          ← git clone 根
├── README.md
├── LICENSE
├── .gitignore
├── subgen                       ← Linux / macOS 启动脚本
├── subgen.bat                   ← Windows 启动脚本
├── src/                         ← Python 源码（提交到 git）
│   ├── main.py
│   ├── cli.py
│   ├── interactive.py
│   ├── env.py
│   ├── storage.py
│   ├── network.py
│   ├── subconv.py
│   ├── process.py
│   ├── downloader.py
│   └── presets_data.py
└── data/                        ← 运行时数据（.gitignore）
    ├── bin/subconverter/        ← 下载下来的二进制
    ├── config.toml              ← 全局配置
    ├── presets/                 ← 命名预设（TOML）
    ├── cache/                   ← 远程资源缓存
    └── logs/                    ← subconverter + subgen 日志
```

**不存在**的东西（故意的设计）：

- **没有 `data/state.toml`** —— subgen 不记忆上次的选择。
- **没有 `data/run/`** —— ephemeral 模式不需要 PID 文件。

## 更新

```bash
cd subgen
git pull
```

就这一条。没有 `self-update` 命令。

要刷新打包的 `subconverter` 二进制：

```bash
./subgen install --force
```

ACL4SSR 规则由 `subconverter` 每次转换时现拉，总是最新的。

## 诊断与清理

```bash
./subgen doctor   # 检查 Python 版本、数据目录、二进制、网络
./subgen clean    # 清空 cache 和 logs
```

## License

MIT
