# Material You Icon Pack Addon (Pix Material You 补全包)

面向 Android 13/14+ (PixelOS / AOSP) 的高精度 Material You 动态取色第三方图标全自动补全工程。配合 [Global Icon Pack](https://github.com/richardluo/globalIconPack) (GIP)，无缝热补全 PashaPuma `Pix Material You` 等主流主题包缺失的第三方应用图标。

本项目是一个 **100% 本地确定性、自闭环的工具链工程**。无论是人类开发者还是 AI Agent（如 GrokBot、Claude 等），均可通过标准命令行一条指令完成“**设计图提取 → 矢量轮廓解析 → MD3 双色分层 → Android 资源装配 → AAPT2 编译签名 → GIP 数据库热注入 → 桌面缓存刷新**”的全流程。

---

## 目录

- [一、架构设计与目录结构](#一架构设计与目录结构)
- [二、运行环境与安装指南](#二运行环境与安装指南)
- [三、核心算法与工程规范](#三核心算法与工程规范)
- [四、CLI 常用命令指南](#四cli-常用命令指南)
- [五、AI Agent (GrokBot) 协作与自动化工作流](#五ai-agent-grokbot-协作与自动化工作流)
- [六、常见问题排查 (FAQ)](#六常见问题排查-faq)

---

## 一、架构设计与目录结构

工程采用**高内聚、低耦合**的模块化架构，核心逻辑分层清晰，统一由根目录的 [`craft.py`](craft.py) 驱动：

```
.
├── craft.py                  # CLI 主入口 (add, build, deploy, reset, list)
├── core/                     # 核心服务模块
│   ├── env.py                # 跨平台工具链动态自适应探测 (ImageMagick, aapt2, SDK 等)
│   ├── vectorizer.py         # 位图转矢量、MD3 双色提取、绝对几何居中引擎
│   ├── builder.py            # Android 资源装配、AAPT2 编译与 APK 自动签名服务
│   ├── deployer.py           # ADB 自动化安装、GIP 数据库热注入与桌面缓存重置
│   └── resolver.py           # 智能组件识别 (本地词库 + ADB 实时容错匹配)
├── android/                  # Android 基础工程骨架
│   ├── AndroidManifest.xml   # 补丁包清单 (包名: com.materialyou.honorofkings.addon)
│   ├── assets/               # appfilter.xml 与 drawable.xml 规则索引
│   └── res/                  # 资源目录 (drawable, drawable-anydpi-v26/v33, values 动态取色定义)
├── assets/                   # 生成的各应用 SVG 矢量源文件 (sky, dark, fg, mono)
├── output/                   # 产物输出目录 (已签名的 MaterialYou_Addon.apk 及 512px 高清 PNG)
├── data/                     # 数据与配置存储
│   ├── manifest.json         # 已收录应用元数据清单 (包名、组件、相对路径)
│   └── components.json       # 离线组件包名库
├── tools/                    # 打包签名固定依赖
│   ├── apksigner.jar         # APK 签名程序
│   └── release.jks           # 签名密钥库 (别名: addon, 密码: materialyou)
├── AGENTS.md                 # 专为 AI Agent 编写的协作与维护准则
└── README.md                 # 项目完整使用与开发文档
```

---

## 二、运行环境与安装指南

本工程通过 [`core/env.py`](core/env.py) 实现了跨平台工具链自适应嗅探，**无需修改任何代码**，只需确保系统安装了以下依赖并配置好环境变量：

### 1. 核心依赖清单

| 依赖项 | 最低版本 | 用途说明 | 获取方式 |
| :--- | :--- | :--- | :--- |
| **Python** | 3.9+ | 运行核心流水线脚本（全流程仅用标准库，**无需 pip 安装额外三方库**） | 系统包管理器 |
| **Java (JRE/JDK)** | 11+ | 运行 `tools/apksigner.jar` 自动签署生成的 APK | 系统包管理器 |
| **ImageMagick** | 7.x | 图像预处理、外圈底板过滤、色彩直方图聚类分析 (`magick` / `convert`) | 系统包管理器 |
| **Potrace** | 1.16+ | 高精度位图矢量化引擎，提取贝塞尔平滑轮廓 | 系统包管理器 |
| **resvg** | 0.40+ | 高性能 SVG 渲染器，生成 512px 预览图及 Android drawable PNG | 系统包管理器 / cargo |
| **AAPT2** | 8.x+ | Android Asset Packaging Tool，编译 XML 资源并链接 APK | Android SDK / 系统包 |
| **android.jar** | API 33+ | Android 平台框架符号库（推荐 Android 13/14） | Android SDK platforms |
| **ADB** | 1.0.41+ | 与 Android 真机通信，读取组件信息及执行热注入 | 系统包管理器 |

### 2. 各操作系统安装命令

#### Ubuntu / Debian：
```bash
sudo apt update
sudo apt install -y python3 openjdk-17-jre imagemagick potrace cargo adb aapt

# 安装 resvg CLI
cargo install resvg --locked

# 配置 Android SDK (或直接使用已有 Android Studio 的 SDK)
export ANDROID_HOME=$HOME/Android/Sdk
# 确保包含 platforms/android-34/android.jar
```

#### Arch Linux：
```bash
sudo pacman -S python jre-openjdk imagemagick potrace resvg android-tools android-sdk-build-tools

# 配置环境变量
export ANDROID_HOME=/opt/android-sdk
```

#### NixOS：
在 `configuration.nix` 或 `shell.nix` 中引入：
```nix
pkgs.mkShell {
  buildInputs = with pkgs; [
    python3
    openjdk17
    imagemagick
    potrace
    resvg
    android-tools
  ];
}
```

### 3. 环境变量配置说明

[`core/env.py`](core/env.py) 会按如下优先级自动定位工具：
1. **AAPT2**：优先检查系统 `PATH` → `$ANDROID_HOME/build-tools/*/aapt2` → `~/Android/Sdk/build-tools/*/aapt2`。
2. **android.jar**：优先检查 `$ANDROID_JAR` 环境变量 → `$ANDROID_HOME/platforms/*/android.jar` → `~/Android/Sdk/platforms/*/android.jar`。
3. **ImageMagick / Potrace / resvg**：直接使用系统 `PATH` 中的二进制。

> [!TIP]
> 如果你的 Android SDK 安装在非标准路径，只需在 `~/.bashrc` 或 `~/.zshrc` 中添加：
> ```bash
> export ANDROID_HOME="/path/to/your/android-sdk"
> ```

---

## 三、核心算法与工程规范

### 1. 绝对几何居中算法 (Zero Centroid Drift)
* **严禁加权物理质心**：宽底窄顶图形（人物、云朵、窗口）由于底部像素密集，使用质心 $\sum y / N$ 会导致重心下偏，算法会将其错误强行抬升。必须使用**联合包围盒最小外接矩形中心**。
* **联合投影去噪**：提取主色与辅色层二进制位图并求并集（$\text{Mask}_{\text{pri}} \cup \text{Mask}_{\text{sec}}$），采用行列投影直方图过滤 $< 4\text{px}$ 的孤立抗锯齿毛刺与噪点，确定绝对外接包围盒 $[x_{\min}, x_{\max}, y_{\min}, y_{\max}]$。
* **Transform 变换闭环**：
  $$\text{transform} = \text{translate}(512, 512) \cdot \text{scale}(0.65) \cdot \text{translate}(-c_x, -c_y) \cdot \text{translate}(0, 1024) \cdot \text{scale}(0.1, -0.1)$$
  先将图形几何中心 $(c_x, c_y)$ 严格对准坐标原点，再等比缩放至 65% 安全区，最后平移至画布正中 $(512.0, 512.0)$。彻底杜绝绕画布中心缩放产生的 $(1 - 0.65) \times (c_x - 512)$ 漂移杠杆误差。

### 2. 复合图标主元素视觉对齐 (`VISUAL_CENTER_OVERRIDES`)
对于“核心主体 + 右下角角标”的复合图形（如 MiPush 铃铛+芯片、Hide Thanox 大盾牌+眼睛徽章、SukiSU 猫脸+盾标），机械外接矩形会将整体拉偏。
在 [`core/vectorizer.py`](core/vectorizer.py) 的 `VISUAL_CENTER_OVERRIDES` 中以核心主体对称轴（$x=512.0$）和主体纵向中心为基准锚定居中，角标自然悬挂于右下角，保持平衡美感。

### 3. MD3 动态取色规范与分层机制
* **原生底板过滤**：连通区域像素数 $> 220,000$（占整幅画布 20% 以上）判定为输入图片自带的浅色背景底圆，自动过滤丢弃。
* **色彩契约（与 PashaPuma 动态取色 100% 对齐）**：
  * **浅色模式**：浅天青背景容器 (`#BAEAFF`) + 深青色主色 (`#004D62`) + 次深青辅色 (`#416D7D`)。
  * **深色模式**：暗墨青背景容器 (`#1D3138`) + 浅天青主色 (`#BAEAFF`) + 中青灰辅色 (`#7595A3`)。
* **动态取色与单色剪影 (Monochrome)**：
  每个图标自动生成 3 款位图资源：完整双色位图 (`ic_xxx.png`)、透明前景 (`ic_xxx_fg.png`) 与纯白单色剪影 (`ic_xxx_mono.png`)。
  在 `drawable-anydpi-v26` 与 `drawable-anydpi-v33` 的 XML 中标准声明：
  ```xml
  <adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
      <background android:drawable="@color/bg_themed_icons" />
      <foreground>
          <bitmap android:src="@drawable/ic_xxx_mono" android:tint="@color/fg_themed_icons" />
      </foreground>
      <monochrome android:drawable="@drawable/ic_xxx_mono" />
  </adaptive-icon>
  ```
  完美支持 Android 13+ 通知栏单色剪影与桌面 Material You 动态随壁纸变色。

### 4. GIP 数据库热注入与防脏写机制
* **二进制 BLOB 格式**：Global Icon Pack 的数据库表中，`entry` 字段严格保存为：
  `\x00` + 大端序双字节字符串长度 (`struct.pack(">H", len(name))`) + UTF-8 编码的 drawable 资源名。
* **双向兜底映射**：每款应用同时注入完整组件精准匹配 `(pkg, act)` 以及包级别回退匹配 `(pkg, "")`。
* **防脏写生命周期锁**：在提取和回推 `iconPack.db` 前后，均执行 `am force-stop com.richardluo.globalIconPack` 切断常驻进程内存连接，杜绝后台缓存覆盖回退；完成后同步更新 `iconPack.db.bak` 并校正 `nobody:nobody` 权限。
* **桌面刷新时序**：清理 `/data/data/com.google.android.apps.nexuslauncher/databases/app_icons.db*` 并 `killall com.google.android.apps.nexuslauncher`，Launcher 重启后即可实时渲染最新矢量。

---

## 四、CLI 常用命令指南

所有日常操作通过 `craft.py` 即可完成：

```bash
# 1. 添加单个图标并自动部署至连接的手机
python3 craft.py add /path/to/icon.png com.example.app "应用名称" --deploy

# 2. 如果存在多个已连接设备，可明确指定设备序列号
python3 craft.py add /path/to/icon.png com.example.app "应用名称" --deploy --device <DEVICE_ID>

# 3. 仅重新编译签名当前 APK
python3 craft.py build

# 4. 重新将当前包热注入至手机并刷新 Launcher 缓存
python3 craft.py deploy

# 5. 查看当前已收录的应用清单
python3 craft.py list

# 6. 清空重置工程（清空历史应用，仅保留基础 logo）
python3 craft.py reset
```

---

## 五、AI Agent (GrokBot) 协作与自动化工作流

若由 AI Agent（如 GrokBot）接管或协同维护本工程，遵循以下工作流：

```mermaid
flowchart TD
    A[用户发送图标设计图与包名] --> B[GrokBot 检查并保存图片到本地临时目录]
    B --> C[调用 python3 craft.py add <path> <pkg> [name] --deploy]
    C --> D[验证 ADB 部署输出与退出码]
    D --> E[使用 adb exec-out screencap -p 本地截图校验]
    E --> F[汇报完成并附带预览效果]
```

### Agent 运维硬性约束：
1. **零残留与隐私边界**：
   * 严禁在用户手机 `/sdcard/` 留下中间文件或截图，截图必须使用 `adb exec-out screencap -p` 直接管道输出至 PC 本地。
   * 临时传输的 `/data/local/tmp` 临时文件必须在任务结束时彻底清理。
2. **规范提交信息**：
   Git 提交必须使用中文 Conventional Commits 格式（例如 `feat(icon): 新增雨课堂 Material You 图标`）。
3. **最小改动**：
   除非遇到全新的边缘形态，不要轻易改动 `core/` 下的底层通用变换矩阵与分层算法。

---

## 六、常见问题排查 (FAQ)

### Q1: 部署后部分图标在 Launcher 上没变色？
1. 检查 Pixel Launcher 缓存是否被清空：`adb shell su -c 'rm -f /data/data/com.google.android.apps.nexuslauncher/databases/app_icons.db* && killall com.google.android.apps.nexuslauncher'`。
2. 检查应用是否使用了非标准启动别名（例如 `.ui.MainActivityAlias`）。可以通过 `adb shell cmd package resolve-activity --brief <包名>` 查看真机实际入口，并在 `data/manifest.json` 中修正。

### Q2: 出现多台设备连接时如何处理？
[`core/resolver.py`](core/resolver.py) 与 [`core/deployer.py`](core/deployer.py) 内置了多设备智能嗅探，会优先选取装有 `com.richardluo.globalIconPack` 的目标手机；你也可以通过 `--device <序列号>` 显式指定目标设备。

### Q3: 为什么通知栏图标有时呈现外圈白圆？
这是 Android 系统通知（SystemUI）在应用全局图标包时的标准行为：系统对通知容器统一裁剪为圆底，若原应用本身没有向 `setSmallIcon` 注册专用的 24dp 剪影，SystemUI 会使用主题包的单色 Adaptive 图标进行绘制。本项目生成的单色剪影层 `ic_xxx_mono` 与 PashaPuma 原生规格 100% 相同。
