# subgen

> Portable, folder-based interactive wrapper for [subconverter](https://github.com/MetaCubeX/subconverter).
> Clone-and-run, no installation, no system services, no domestic mirrors.
>
> [简体中文](#中文说明)

## What is this

`subgen` is a CLI tool that wraps the local `subconverter` HTTP service to:

- Fetch your airport (机场) subscription with a chosen network mode (direct or via proxy)
- Convert it to a Clash / Clash.Meta YAML using preset rule packages (ACL4SSR variants)
- Tag the converted output with `[SG] ` prefix so you can distinguish it in your Clash client
- Persist your last choice as the default for next run

Everything lives in the cloned folder. Nothing touches `~/.config/`, `~/.local/`, `%APPDATA%`, etc.

## Quick start

### Linux / macOS

```bash
git clone https://github.com/Rannk2085/subgen.git
cd subgen
./subgen
```

### Windows

```cmd
git clone https://github.com/Rannk2085/subgen.git
cd subgen
subgen.bat
```

That's it. The first run will:

1. Detect your OS / arch
2. Download `subconverter` binary into `data/bin/subconverter/`
3. Start it as a background process (PID stored in `data/run/`)
4. Drop you into the interactive wizard

## Requirements

- **Python 3.11+** (uses stdlib `tomllib`, no third-party packages)
- Linux / macOS / Windows
- `git` (for cloning + updating via `git pull`)

If `python3` isn't installed:
- Ubuntu/Debian: `sudo apt install python3`
- Windows: `winget install Python.Python.3.12`
- macOS: `brew install python3`

## Commands

```bash
./subgen                       # Interactive wizard (default)
./subgen gen <URL>             # CLI mode, use given URL
./subgen status                # Check subconverter background service
./subgen start                 # Start subconverter
./subgen stop                  # Stop subconverter
./subgen restart               # Restart
./subgen install               # Download/reinstall subconverter binary
./subgen install --force       # Force re-download
./subgen doctor                # Diagnose environment
./subgen version
./subgen help
```

## Folder layout

```
subgen/                      ← git clone root
├── subgen                   ← Linux/macOS launcher (bash)
├── subgen.bat               ← Windows launcher
├── src/                     ← Python source (committed)
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
├── data/                    ← runtime data (.gitignored)
│   ├── bin/subconverter/    ← downloaded binary
│   ├── config.toml          ← global config
│   ├── state.toml           ← last choice memory
│   ├── presets/             ← named presets (TOML)
│   ├── cache/               ← downloaded ACL4SSR rules
│   ├── logs/                ← subconverter + subgen logs
│   └── run/                 ← PID file
└── README.md
```

## Network modes

When you run the wizard, step 2 asks how to fetch the subscription URL:

| Mode | What it does | When to use |
|---|---|---|
| **DIRECT** | curl-equivalent direct connection (no proxy) | Your machine has the right outgoing IP for this airport |
| **PROXY** | Routes through `http://127.0.0.1:7890` (Clash Party default) | Subscription is overseas-only |
| **CUSTOM** | Routes through user-supplied proxy URL | Special setups |

`subgen` does **not** modify your system proxy. It only **detects** the current state and **suggests** which mode to use, with notes for each. You're responsible for switching modes in your Clash client / system if needed.

## Rule presets

Step 3 lets you choose an ACL4SSR variant. Each variant defines a different set of proxy groups + rules in the generated YAML:

| Preset | Groups | Rules | Notes |
|---|---|---|---|
| **Full** ⭐ | 19 | ~10000 | Full coverage, recommended |
| Mini | 5 | ~4000 | Minimal, fast startup |
| Full + AdblockPlus | 19 | ~12000 | Aggressive ad blocking |
| Full NoAuto | 18 | ~10000 | No url-test (manual select only) |
| NoApple | 18 | ~9500 | Apple services go DIRECT |
| NoAuto NoFakeIP | 18 | ~10000 | For special network setups |
| Mini Fallback | 5 | ~4000 | fallback instead of url-test |
| WithGFW | 6 | ~8000 | GFW List based |
| Custom | - | - | Manually input ini URL |

## Naming convention

The converted subscription is named with format `[SG] <derived-name>`. For example, fetching `https://link01.nobodys.uk/...` produces a config named `[SG] link01` when imported into Clash for Windows / Mihomo Party.

The `[SG]` prefix is hardcoded (= SubGen) and not configurable. It exists only to distinguish "this profile was converted by subgen" from any original profile.

## Updating

```bash
cd subgen
git pull
```

That's the entire update mechanism. No `self-update` command, no binary replacement.

To update the bundled subconverter binary:
```bash
./subgen install --force
```

To update ACL4SSR rules: they're fetched fresh on every conversion (subconverter handles this).

## Why no mirrors / no installer / no system service

The user requested a strict portable design:

- **No XDG / AppData paths**: everything in `data/` inside the cloned folder
- **No mirrors**: connect to GitHub directly. If you need a proxy, use your existing one (HTTPS_PROXY env or the PROXY mode)
- **No system service**: subconverter runs as a regular detached child process; PID file in `data/run/`
- **No installer**: `git clone && ./subgen` is the entire install
- **No self-update**: `git pull`

This makes subgen identical across all your machines: clone, run, done.

## License

MIT. See [LICENSE](LICENSE).

---

# 中文说明

## 这是什么

`subgen` 是一个**纯文件夹形态、零安装、零系统侵入**的 [subconverter](https://github.com/MetaCubeX/subconverter) 交互式包装工具。

核心功能：
1. 用你选的网络模式（直连 / 代理）拉取机场订阅
2. 调本地 `subconverter` 套用预设规则包（ACL4SSR 系列）转换
3. 自动给转换后的配置加 `[SG] ` 前缀，方便在 Clash 中区分
4. 记忆上次选择，下次回车走默认

所有数据（配置、状态、缓存、日志、subconverter 二进制）都在 clone 的文件夹内，**完全不写系统目录**。

## 三步上手

### Linux / macOS

```bash
git clone https://github.com/Rannk2085/subgen.git
cd subgen
./subgen
```

### Windows

```cmd
git clone https://github.com/Rannk2085/subgen.git
cd subgen
subgen.bat
```

第一次跑会自动：
1. 检测系统/架构
2. 从 GitHub 下载 subconverter 二进制到 `data/bin/`
3. 后台启动 subconverter 子进程
4. 进入交互式向导

## 系统要求

- **Python 3.11+**（用了内置 `tomllib`，无任何第三方依赖）
- Linux / macOS / Windows 都行
- `git`（用于 clone 和更新 `git pull`）

没装 Python？
- Ubuntu/Debian: `sudo apt install python3`
- Windows: `winget install Python.Python.3.12`
- macOS: `brew install python3`

## 命令

```bash
./subgen                   # 交互式向导（最常用）
./subgen gen <URL>         # 命令行模式
./subgen status            # 看 subconverter 状态
./subgen start | stop      # 启停 subconverter
./subgen install           # 下载/重装 subconverter 二进制
./subgen doctor            # 诊断环境
```

## 设计原则

1. **不装系统服务**：subconverter 作为后台子进程，PID 在 `data/run/`
2. **不用国内镜像**：如果你需要代理，用 PROXY 模式或 `HTTPS_PROXY` 环境变量
3. **无安装脚本**：git clone 即装好
4. **无 self-update**：`git pull` 就是更新
5. **跨设备一致**：在任何机器上 clone 都是同样的体验

## 命名约定

转换后的配置会自动带 `[SG] ` 前缀：

```
原始订阅:   https://link01.nobodys.uk/api/...
导入 Clash: [SG] link01
```

`[SG]` 是硬编码（SubGen 缩写），不可配置。仅用于区分「这是 subgen 转换出来的配置」而已。

## 更新

```bash
cd subgen
git pull
```

就这一条命令。

## License

MIT
