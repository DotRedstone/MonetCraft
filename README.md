# MonetCraft — 通用 Android 图标包补全框架 + AI Skill

面向 Android 的**通用第三方图标包补全框架**，配套开箱即用的 Antigravity Workspace Skill 与 GitHub Actions 自动构建。无论你使用的是 **Material You 动态双色**（Pix Material You / Lawnicons）、**彩色自适应**（Pixel / One UI / HyperOS），还是 **异形 / 线条 / 扁平全彩**（Delta / LineX / Whicons / Crayon），都可以配合 [Global Icon Pack](https://github.com/richardluo/globalIconPack) (GIP)、Pixel Launcher Enhanced (`PLEnhanced`) 或任意支持 `appfilter.xml` 的第三方启动器无缝补齐缺失图标。

## 一、三层解耦架构（框架 + 数据 + Skill）

* **框架层 (`craft.py` + `core/`)**：100% 确定性的本地/CI 流水线，零个人应用硬编码。统一支持 `monet`、`adaptive`、`bitmap` 三种图标规范。
* **数据层 (`pack.json` + `data/` + `assets/`)**：声明式配置与单一源文件仓库（Single Source of Truth）。所有渲染产物（`output/`、`android/res/`）均由 `craft.py build --sync` 自动生成，Git 仅追踪轻量源文件。
* **Skill 层 (`.agents/skills/monetcraft/`)**：面向 AI Agent 的渐进式工作流与多风格设计规范，支持先探测手机当前宿主图标包、再按宿主视觉 DNA 绘制/导入、校验并零残留热部署。

```text
MonetCraft/
├── craft.py                              # 统一 CLI (audit / import / add / sync / build / deploy / verify / list / reset)
├── pack.json                             # 声明式图标包配置 (包名、默认风格 style、色板、签名、动态随机包名规则)
├── core/                                 # 通用框架引擎 (零个人硬编码)
│   ├── config.py                         # 路径常量、pack.json 与 manifest.json 读写
│   ├── env.py                            # 跨平台工具链动态探测 (magick / potrace / resvg / aapt2 / android.jar)
│   ├── adb.py                            # 统一 ADB 封装、多设备嗅探与零残留拉取
│   ├── resolver.py                       # 组件解析、模糊容错与声明式动态包名探测
│   ├── vectorizer.py                     # 多风格图标处理 (monet 矢量化/多层 SVG、adaptive、bitmap)
│   ├── builder.py                        # 从 assets/ 并发重渲染同步、appfilter 生成与零污染隔离编译签名
│   ├── deployer.py                       # APK 覆盖安装、GIP 数据库热注入与 Launcher 缓存重置
│   └── auditor.py                        # 真机宿主包与覆盖率巡检、APK 完整性/Alpha 校验、实机缓存拼图
├── .agents/skills/monetcraft/            # Antigravity Workspace Skill
│   ├── SKILL.md                          # 通用端到端 AI 图标制作与部署工作流
│   └── references/
│       ├── style-monet.md                # Material You / PashaPuma 动态双色 Alpha 与居中规范
│       ├── style-general.md              # 非 MD3 图标包 (Delta/LineX/HyperOS 等) 风格采样与导入指南
│       └── android-stack.md              # PLEnhanced + GIP 双栈原理与零残留边界
├── .github/workflows/build.yml           # GitHub Actions 云端自动构建签名 APK
├── assets/                               # 图标源文件 (SVG / PNG，单一数据源)
├── data/
│   ├── manifest.json                     # 已收录应用清单 (支持单图标 style 覆盖与声明式 aliases)
│   └── components.json                   # 离线组件包名库
├── android/                              # Android APK 模板骨架 (AndroidManifest.xml + appfilter.xml)
├── tools/                                # apksigner.jar 与签名密钥库
└── AGENTS.md                             # 仓库硬性边界约束
```

---

## 二、支持的三类图标风格

在 [`pack.json`](pack.json) 中设置全局 `"style"`，也可在单条图标导入时用 `--style` 单独覆盖：

| 风格 (`style`) | 适用宿主图标包 | 生成资源机制 | 常用导入方式 |
| :--- | :--- | :--- | :--- |
| **`monet`** (默认) | Pix Material You、Lawnicons 等 MD3 动态取色包 | `adaptive-icon` + `@color/bg_themed_icons` + 多 Alpha 透明度 `*_mono.png` 动态着色 | `craft.py import icon_mono.svg <pkg>` / `craft.py add raster.png <pkg>` |
| **`adaptive`** | Pixel、One UI、HyperOS、Nothing 等彩色自适应包 | `adaptive-icon` + 独立背景（`#HEX` 或图）+ 全彩前景 + 可选单色层 | `craft.py import fg.svg <pkg> --style adaptive --bg "#1E88E5"` |
| **`bitmap`** | Delta、LineX、Whicons、Crayon 等异形/线条/扁平包 | 仅写入 `drawable/<name>.png`（无 adaptive XML 裁剪），完整保留轮廓与透明通道 | `craft.py import icon.svg <pkg> --style bitmap` |

---

## 三、CLI 常用命令

```bash
# 1. 巡检已连接手机：识别当前宿主图标包，列出所有未适配桌面应用
python3 craft.py audit

# 2. 导入任意风格图标 (SVG 或 PNG)
python3 craft.py import /path/to/icon_mono.svg com.example.app "应用名" --deploy
python3 craft.py import /path/to/icon.svg com.example.app "应用名" --style bitmap --deploy
python3 craft.py import /path/to/fg.svg com.example.app "应用名" --style adaptive --bg "#1E88E5" --deploy

# 3. 位图自动矢量化为 MD3 双色图标
python3 craft.py add /path/to/icon.png com.example.app "应用名" --deploy

# 4. 从 assets/ 单一数据源并发重建全部 PNG / Android 资源并编译签名 APK
python3 craft.py build --sync

# 5. 部署到设备 (build_tmp 临时合入 SukiSU 等动态随机包名 -> 安装 APK -> 注入 GIP -> 重启桌面)
python3 craft.py deploy

# 6. 校验 APK 资源完整性与 Monet 多层 Alpha 质量，并可选导出真机缓存拼图
python3 craft.py verify --out /tmp/device_verify.png
```

---

## 四、云端自动化构建 (GitHub Actions)

本仓库内置 [`.github/workflows/build.yml`](.github/workflows/build.yml)，无需本地 Android SDK：
* 推送新的图标源文件到 `assets/` 并更新 `data/manifest.json` 后，Actions 会自动安装工具链、执行 `python3 craft.py build --sync` 与 `craft.py verify`，并将签好名的 APK 作为 Artifact 输出。
* 签名密码支持通过仓库 Secret `MONETCRAFT_KS_PASS` 覆盖。

---

## 五、本地环境依赖

仅需 Python 3.9+ 标准库（零 `pip` 依赖），外部二进制由 [`core/env.py`](core/env.py) 自动从 `PATH` / `$ANDROID_HOME` 探测：
* `java` (11+) · `magick` / `convert` (ImageMagick 7) · `potrace` · `resvg` · `aapt2` · `android.jar` · `adb`（仅真机巡检与热部署需要）

---

## 六、配合 AI Agent 使用

在支持 `.agents/skills/` 的 Coding Agent（如 Antigravity）中打开本仓库，Agent 会自动加载 [`monetcraft`](.agents/skills/monetcraft/SKILL.md) Skill。你可以直接说：
* 「巡检一下我手机哪些图标没适配，按当前宿主图标包风格补齐并部署」
* 「我换成了 LineX / Delta 图标包，帮我给这几个 App 补一套同风格图标」
