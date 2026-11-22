# AGENTS.md - MonetCraft 仓库协作边界

本文件仅定义本仓库的硬性工程约束。完整的图标排查、多层双色设计、SVG 导入、打包验证与部署 SOP 已封装在 Workspace Skill [`.agents/skills/monetcraft/SKILL.md`](.agents/skills/monetcraft/SKILL.md) 中，执行相关任务时请加载该 Skill。

## 1. 代码与协作硬性约束

* **语言**：默认使用中文回复；技术名词、命令、文件路径及标识符保留英文。
* **最小必要改动**：修 bug 只修 bug；重构不改变外部行为；发现无关问题先指出，不擅自顺手修改。
* **低耦合、高内聚**：
  * `core/` 为通用图标包框架，禁止写死个人应用特判或设备私有包名。
  * 图标包元数据、动态探测规则与视觉居中覆盖统一声明在 [`pack.json`](pack.json)。
  * 应用映射与多变体别名统一声明在 [`data/manifest.json`](data/manifest.json)（`aliases` 字段）。
* **注释与提交**：注释仅简短标注模块区域（如 `# [Service]`、`# [Constants]`）；Git commit message 必须遵循中文 Conventional Commits（如 `feat(core): ...`、`fix(icon): ...`）。
* **严格验证**：声称完成前必须实际执行对应命令或校验步骤，禁止假设通过。

## 2. 手机端零残留与隐私边界

* **严禁污染 `/sdcard/`**：截图必须使用 `adb exec-out screencap -p` 直接管道输出到 PC 本地。
* **严禁遗留临时文件**：经由 `/data/local/tmp/` 中转的 `.db` / `.tmp` 文件必须在 `finally` 块中 `rm -f` 彻底清理。
* **严禁泄露设备私有数据到 Git**：随机包名应用的临时映射仅在 `build_tmp/staged_assets/` 参与编译，禁止写入跟踪中的 `android/assets/appfilter.xml` 或 `data/manifest.json`。
