# AGENTS.md - AI Agent 协作与维护规范

本文件专为接手或参与本仓库开发的 AI Agent 编写。在执行任何改动、新增图标或调用工具前，必须严格遵守以下准则。

---

## 1. 核心准则与行为约束

* **语言偏好**：默认使用中文回复。技术专有名词、命令、文件名及代码接口保留英文。
* **最小必要改动**：禁止顺手重写无关代码；修 bug 只修 bug；重构不改变既有外部行为；发现无关问题先提示，禁止擅自一起改。
* **低耦合、高内聚**：单一模块专注单一职责，禁止为了所谓的“复用”引入过度抽象与隐式副作用。
* **注释风格**：保持简短结构化，仅标注功能块（如 `# [Service]`, `# [Constants]`），不要写长篇大论或重复代码细节的注释。
* **提交信息**：遵循 Conventional Commits 规范，统一中文说明（例如 `feat(core): 支持 ...`，`fix(align): 修复 ...`）。
* **严格验证**：声称完成前必须实际执行过对应测试/命令，禁止凭空假设测试已通过。
* **手机端零残留与隐私边界**：
  * 严禁在用户手机 `/sdcard/` 留下截图。截图必须使用 `adb exec-out screencap -p` 直接输出至 PC 本地。
  * 临时传输的中间文件（如 `/data/local/tmp/iconPack.db`）在任务结束时必须执行 `rm -f` 彻底清理。

---

## 2. 运行环境与工具链依赖

本工程已通过 [`core/env.py`](core/env.py) 实现跨平台工具链动态自适应探测，优先使用系统 PATH 或标准环境变量：

* **ImageMagick**：系统命令 `magick` 或 `convert`（NixOS 兜底路径已预置）
* **Potrace**：系统命令 `potrace`（提取矢量贝塞尔曲线）
* **resvg**：系统命令 `resvg`（渲染高质量预览图与位图）
* **AAPT2**：自动检测系统 PATH、`$ANDROID_HOME/build-tools/` 或 NixOS 兜底
* **Android SDK Jar**：自动读取 `$ANDROID_JAR`、`$ANDROID_HOME/platforms/` 或 `~/Android/Sdk/platforms/`
* **ApkSigner**：`tools/apksigner.jar`（密钥库 `tools/release.jks`，别名 `addon`，密码 `materialyou`）

---

## 3. 核心领域知识与避坑指南

### 3.1 严格几何居中 (Transform Order)
* **禁忌**：切勿使用 `translate(512, 512) scale(0.65) translate(-512, -512)` 绕画布物理中心缩放，这样会产生 $(1 - 0.65) \times (c_x - 512)$ 的漂移放大误差。
* **正确做法**：先求出外接矩形几何中心 $(c_x, c_y)$，将其对齐至坐标原点，再等比缩放，最后平移至画布正中：
  `translate(512, 512) scale(0.65) translate(-cx, -cy) translate(0, 1024) scale(0.1, -0.1)`。
* **禁忌**：严禁用物理重心 $\sum y / N$（质心），宽底窄顶图形（人物、云朵、窗口）会因下部像素密度大导致质心下偏进而被算法强行抬升。必须使用联合包围盒外接矩形中心。

### 3.2 杂色与背景底圆过滤
* **面积过滤**：如果聚类出的图层像素数 $> 220,000$（占整幅画布 $20\%$ 以上），判定为原生底板（如米窗自带浅色底圆），必须过滤丢弃。
* **边缘去噪**：包围盒计算采用行列投影直方图，且像素密度阈值 $\ge 4\text{px}$，避免压缩毛刺将包围盒边缘撑大。

### 3.3 Global Icon Pack (GIP) 二进制格式
* 远程数据库路径：`/data/misc/com.richardluo.globalIconPack/iconPack.db`。
* 数据库表中存储的 `entry` 字段为二进制 BLOB，格式严格为：
  `\x00` + 大端序双字节字符串长度 (`struct.pack(">H", len(name))`) + UTF-8 编码的资源名。
* 映射必须同时写入组件精确匹配 `(pkg, act)` 以及包级别后备 `(pkg, "")`。

### 3.4 Pixel Launcher 缓存重置序列
在覆盖安装 APK 或热更新 GIP 数据库后，必须依次执行：
1. `rm -f /data/data/com.google.android.apps.nexuslauncher/databases/app_icons.db*`
2. `killall com.google.android.apps.nexuslauncher`
等待 Launcher 自动拉起即可刷新最新矢量图标。

---

## 4. 常用运维与构建命令

```bash
# 添加新图标并自动部署
python3 craft.py add <image_path> <pkg_or_name> [custom_name] --deploy

# 仅重新打包签名并部署
python3 craft.py build --deploy

# 重新将当前包热注入至手机并刷新缓存
python3 craft.py deploy

# 检查当前已收录应用
python3 craft.py list
```
