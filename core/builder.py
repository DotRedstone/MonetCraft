#!/usr/bin/env python3
# [Builder]
# 通用 Android 图标包装配引擎：支持 monet / adaptive / bitmap 三种风格与零污染隔离编译

from concurrent.futures import ThreadPoolExecutor
import os
import shutil
import subprocess

from core.config import (
    ANDROID_ASSETS_DIR,
    ANDROID_DIR,
    ANDROID_RES_DIR,
    ASSETS_DIR,
    BUILD_TMP_DIR,
    OUTPUT_DIR,
    TOOLS_DIR,
    load_pack_config,
    resolve_path,
)
from core.env import AAPT2, ANDROID_JAR
from core.vectorizer import IconVectorizer

# [Constants]
APKSIGNER_JAR = os.path.join(TOOLS_DIR, "apksigner.jar")


# [Helpers]
def _expand_component(pkg, act):
    comps = [f"{pkg}/{act}"]
    if act.startswith(pkg):
        rel = act[len(pkg):]
        if not rel.startswith("."):
            rel = "." + rel
        comps.append(f"{pkg}/{rel}")
    elif act.startswith("."):
        comps.append(f"{pkg}/{pkg}{act}")
    else:
        comps.append(f"{pkg}/.{act}")
    return comps


def build_appfilter_xml(items):
    """生成标准 appfilter.xml 与 drawable.xml 文本内容"""
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]
    drawable_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<resources>",
        "    <version>1</version>",
        '    <category title="Addons" />',
    ]
    seen_drawables = set()

    for it in items:
        pkg = it["pkg"]
        act = it["activity"]
        drw = it["drawable"]
        name = it.get("name", pkg)

        if drw not in seen_drawables:
            drawable_lines.append(f'    <item drawable="{drw}" />')
            seen_drawables.add(drw)

        comps = []
        comps.extend(_expand_component(pkg, act))
        comps.append(f"{pkg}/.{act.split('.')[-1]}")
        comps.append(f"{pkg}/{pkg}.MainActivity")
        comps.append(f"{pkg}/.MainActivity")

        for alias in it.get("aliases", []):
            if "/" in alias:
                apkg, aact = alias.split("/", 1)
                comps.extend(_expand_component(apkg, aact))

        added = set()
        for c in comps:
            if c not in added:
                lines.append(f'    <item component="ComponentInfo{{{c}}}" drawable="{drw}" name="{name}" />')
                added.add(c)

    lines.append("</resources>")
    drawable_lines.append("</resources>")
    return "\n".join(lines) + "\n", "\n".join(drawable_lines) + "\n"


def _remove_if_exists(path):
    if os.path.exists(path):
        os.remove(path)


# [Service]
class ApkBuilder:
    def __init__(self, pack_config=None):
        self.cfg = pack_config or load_pack_config()
        self.default_style = self.cfg.get("style", "monet")
        self.ensure_dirs()
        self.ensure_color_resources()

    def ensure_dirs(self):
        for d in (
            "drawable",
            "drawable-anydpi-v26",
            "drawable-anydpi-v33",
            "values",
            "values-night",
            "values-v31",
            "values-night-v31",
        ):
            os.makedirs(os.path.join(ANDROID_RES_DIR, d), exist_ok=True)
        os.makedirs(ANDROID_ASSETS_DIR, exist_ok=True)
        os.makedirs(BUILD_TMP_DIR, exist_ok=True)

    def ensure_color_resources(self):
        """写入动态取色与浅/深色回退色板 (读取自 pack.json palette)"""
        pal = self.cfg["palette"]
        color_files = {
            ("values", "colors.xml"): f"""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="bg_themed_icons">{pal['light_bg']}</color>
    <color name="fg_themed_icons">{pal['light_fg']}</color>
    <color name="ic_bg">{pal['light_bg']}</color>
    <color name="ic_fg">{pal['light_fg']}</color>
    <color name="ic_bg_sky">{pal['light_bg']}</color>
    <color name="ic_launcher_bg">{pal['light_bg']}</color>
    <color name="ic_launcher_fg">{pal['light_fg']}</color>
    <color name="ic_launcher_mono">#FFFFFF</color>
</resources>
""",
            ("values-night", "colors.xml"): f"""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="bg_themed_icons">{pal['dark_bg']}</color>
    <color name="fg_themed_icons">{pal['dark_fg']}</color>
    <color name="ic_bg">{pal['dark_bg']}</color>
    <color name="ic_fg">{pal['dark_fg']}</color>
</resources>
""",
            ("values-v31", "colors.xml"): """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="bg_themed_icons">@android:color/system_accent1_100</color>
    <color name="fg_themed_icons">@android:color/system_accent1_700</color>
    <color name="ic_bg">@android:color/system_accent1_100</color>
    <color name="ic_fg">@android:color/system_accent1_700</color>
</resources>
""",
            ("values-night-v31", "colors.xml"): """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="bg_themed_icons">@android:color/system_accent2_800</color>
    <color name="fg_themed_icons">@android:color/system_accent1_200</color>
    <color name="ic_bg">@android:color/system_accent2_800</color>
    <color name="ic_fg">@android:color/system_accent1_200</color>
</resources>
""",
        }
        for (folder, filename), content in color_files.items():
            with open(os.path.join(ANDROID_RES_DIR, folder, filename), "w", encoding="utf-8") as f:
                f.write(content)

    def ensure_manifest_xml(self):
        """同步 pack.json 元数据至 AndroidManifest.xml"""
        pkg = self.cfg["package_name"]
        label = self.cfg["label"]
        vcode = self.cfg.get("version_code", 1)
        vname = self.cfg.get("version_name", "1.0")
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{pkg}"
    android:versionCode="{vcode}"
    android:versionName="{vname}">

    <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="34" />

    <application
        android:label="{label}"
        android:icon="@drawable/ic_pack_logo"
        android:hasCode="false">

        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
            </intent-filter>
            <intent-filter>
                <action android:name="org.adw.launcher.THEMES" />
                <category android:name="android.intent.category.DEFAULT" />
            </intent-filter>
            <intent-filter>
                <action android:name="com.novalauncher.THEME" />
                <category android:name="android.intent.category.DEFAULT" />
            </intent-filter>
            <intent-filter>
                <action android:name="ch.deletescape.lawnchair.ICONPACK" />
                <category android:name="android.intent.category.DEFAULT" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"""
        with open(os.path.join(ANDROID_DIR, "AndroidManifest.xml"), "w", encoding="utf-8") as f:
            f.write(xml)

    def clean_icons(self, keep_pack_logo=True):
        """清空应用图标资源目录"""
        for d in ("drawable", "drawable-anydpi-v26", "drawable-anydpi-v33"):
            target_dir = os.path.join(ANDROID_RES_DIR, d)
            if not os.path.exists(target_dir):
                continue
            for item in os.listdir(target_dir):
                if keep_pack_logo and item.startswith("ic_pack_logo"):
                    continue
                path = os.path.join(target_dir, item)
                if os.path.isfile(path) or os.path.islink(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
        self.ensure_color_resources()
        self.write_appfilter([])

    def add_icon_resource(
        self,
        drawable_name,
        full_png,
        fg_png=None,
        mono_png=None,
        style=None,
        bg_png=None,
        bg_color=None,
    ):
        """
        按风格注册单个图标的 Android 资源：
        - monet:    drawable PNG + 动态着色 adaptive-icon XML (v26/v33)
        - adaptive: 彩色前景 + 纯色/图片背景 + 可选单色层 adaptive-icon XML (v26/v33)
        - bitmap:   纯位图 drawable/<name>.png，不生成 adaptive-icon XML，保留异形与透明轮廓
        """
        resolved_style = style or self.default_style
        shutil.copyfile(full_png, os.path.join(ANDROID_RES_DIR, "drawable", f"{drawable_name}.png"))

        if resolved_style == "bitmap":
            for suffix in ("_fg.png", "_bg.png", "_mono.png"):
                _remove_if_exists(os.path.join(ANDROID_RES_DIR, "drawable", f"{drawable_name}{suffix}"))
            for folder in ("drawable-anydpi-v26", "drawable-anydpi-v33"):
                _remove_if_exists(os.path.join(ANDROID_RES_DIR, folder, f"{drawable_name}.xml"))
            return

        if resolved_style == "adaptive":
            if not fg_png:
                raise ValueError(f"adaptive 风格图标缺少前景 PNG: {drawable_name}")
            shutil.copyfile(fg_png, os.path.join(ANDROID_RES_DIR, "drawable", f"{drawable_name}_fg.png"))
            if bg_png:
                shutil.copyfile(bg_png, os.path.join(ANDROID_RES_DIR, "drawable", f"{drawable_name}_bg.png"))
                bg_block = f'    <background android:drawable="@drawable/{drawable_name}_bg" />'
            else:
                color_val = bg_color or "#FFFFFF"
                bg_block = (
                    "    <background>\n"
                    f'        <color android:color="{color_val}" />\n'
                    "    </background>"
                )
            mono_block = ""
            if mono_png:
                shutil.copyfile(mono_png, os.path.join(ANDROID_RES_DIR, "drawable", f"{drawable_name}_mono.png"))
                mono_block = f'\n    <monochrome android:drawable="@drawable/{drawable_name}_mono" />'

            adaptive_xml = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                f"{bg_block}\n"
                f'    <foreground android:drawable="@drawable/{drawable_name}_fg" />'
                f"{mono_block}\n"
                "</adaptive-icon>\n"
            )
            for folder in ("drawable-anydpi-v26", "drawable-anydpi-v33"):
                with open(os.path.join(ANDROID_RES_DIR, folder, f"{drawable_name}.xml"), "w", encoding="utf-8") as f:
                    f.write(adaptive_xml)
            return

        # 默认 monet 风格
        if not (fg_png and mono_png):
            raise ValueError(f"monet 风格图标缺少 fg/mono PNG: {drawable_name}")
        shutil.copyfile(fg_png, os.path.join(ANDROID_RES_DIR, "drawable", f"{drawable_name}_fg.png"))
        shutil.copyfile(mono_png, os.path.join(ANDROID_RES_DIR, "drawable", f"{drawable_name}_mono.png"))

        adaptive_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/bg_themed_icons" />
    <foreground>
        <bitmap
            android:src="@drawable/{drawable_name}_mono"
            android:tint="@color/fg_themed_icons" />
    </foreground>
    <monochrome android:drawable="@drawable/{drawable_name}_mono" />
</adaptive-icon>
"""
        for folder in ("drawable-anydpi-v26", "drawable-anydpi-v33"):
            with open(os.path.join(ANDROID_RES_DIR, folder, f"{drawable_name}.xml"), "w", encoding="utf-8") as f:
                f.write(adaptive_xml)

    def _sync_pack_logo(self, vectorizer, assets_dir, output_dir):
        """确保干净克隆下也能从 assets/ic_pack_logo* 自动重建应用本身图标"""
        logo_name = "ic_pack_logo"
        if os.path.exists(os.path.join(assets_dir, f"{logo_name}_mono.svg")):
            res = vectorizer.render_from_assets(logo_name, assets_dir, output_dir, style="monet")
            self.add_icon_resource(
                logo_name, res["normal_png"], res.get("fg_png"), res.get("mono_png"), style="monet"
            )
        elif os.path.exists(os.path.join(assets_dir, f"{logo_name}.svg")) or os.path.exists(
            os.path.join(assets_dir, f"{logo_name}.png")
        ):
            res = vectorizer.render_from_assets(logo_name, assets_dir, output_dir, style="bitmap")
            self.add_icon_resource(logo_name, res["normal_png"], style="bitmap")

    def sync_from_assets(self, manifest, assets_dir=ASSETS_DIR, output_dir=OUTPUT_DIR):
        """从 assets/ 单一数据源并发重渲染全部图标及 pack logo，重建完整 android/res/"""
        self.clean_icons(keep_pack_logo=False)
        self.ensure_manifest_xml()
        vectorizer = IconVectorizer(os.path.join(BUILD_TMP_DIR, "sync_work"), pack_config=self.cfg)
        self._sync_pack_logo(vectorizer, assets_dir, output_dir)

        tasks = []
        seen = set()
        for it in manifest:
            drw = it["drawable"]
            if drw in seen:
                continue
            seen.add(drw)
            style = it.get("style", self.default_style)
            bg_color = it.get("bg_color")
            tasks.append((drw, style, bg_color))

        def _render_one(task):
            drw, style, bg_color = task
            res = vectorizer.render_from_assets(drw, assets_dir, output_dir, style=style, bg_color=bg_color)
            return drw, style, res

        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as pool:
            for drw, style, res in pool.map(_render_one, tasks):
                self.add_icon_resource(
                    drw,
                    res["normal_png"],
                    fg_png=res.get("fg_png"),
                    mono_png=res.get("mono_png"),
                    style=style,
                    bg_png=res.get("bg_png"),
                    bg_color=res.get("bg_color"),
                )

        self.write_appfilter(manifest)
        return len(tasks)

    def write_appfilter(self, items, target_dir=ANDROID_ASSETS_DIR):
        os.makedirs(target_dir, exist_ok=True)
        appfilter_xml, drawable_xml = build_appfilter_xml(items)
        with open(os.path.join(target_dir, "appfilter.xml"), "w", encoding="utf-8") as f:
            f.write(appfilter_xml)
        with open(os.path.join(target_dir, "drawable.xml"), "w", encoding="utf-8") as f:
            f.write(drawable_xml)

    def build_apk(self, output_apk, base_items=None, extra_items=None):
        """
        执行 aapt2 编译、资源链接与 apksigner 签名。
        若传入 extra_items (设备侧动态随机包名)，仅写入 build_tmp/staged_assets，不污染仓库跟踪文件。
        """
        self.ensure_manifest_xml()
        os.makedirs(os.path.dirname(os.path.abspath(output_apk)), exist_ok=True)
        compiled_zip = os.path.join(BUILD_TMP_DIR, "compiled.zip")
        unaligned_apk = os.path.join(BUILD_TMP_DIR, "unaligned.apk")

        assets_dir_for_link = ANDROID_ASSETS_DIR
        if extra_items:
            staged_assets = os.path.join(BUILD_TMP_DIR, "staged_assets")
            merged = list(base_items or [])
            existing = {(it["pkg"], it["activity"]) for it in merged}
            for item in extra_items:
                if (item["pkg"], item["activity"]) not in existing:
                    merged.append(item)
                    existing.add((item["pkg"], item["activity"]))
            self.write_appfilter(merged, target_dir=staged_assets)
            assets_dir_for_link = staged_assets

        res_compile = subprocess.run(
            [AAPT2, "compile", "--dir", ANDROID_RES_DIR, "-o", compiled_zip],
            capture_output=True,
            text=True,
        )
        if res_compile.returncode != 0:
            raise RuntimeError(f"AAPT2 compile failed: {res_compile.stderr}")

        res_link = subprocess.run(
            [
                AAPT2, "link",
                "-I", ANDROID_JAR,
                "-A", assets_dir_for_link,
                "--manifest", os.path.join(ANDROID_DIR, "AndroidManifest.xml"),
                "--auto-add-overlay",
                "-o", unaligned_apk,
                compiled_zip,
            ],
            capture_output=True,
            text=True,
        )
        if res_link.returncode != 0:
            raise RuntimeError(f"AAPT2 link failed: {res_link.stderr}")

        sign_cfg = self.cfg["signing"]
        ks_path = resolve_path(sign_cfg["keystore"])
        ks_alias = sign_cfg["alias"]
        ks_pass = os.environ.get(
            sign_cfg.get("password_env", "MONETCRAFT_KS_PASS"),
            sign_cfg.get("default_password", ""),
        )

        res_sign = subprocess.run(
            [
                "java", "-jar", APKSIGNER_JAR, "sign",
                "--ks", ks_path,
                "--ks-key-alias", ks_alias,
                "--ks-pass", f"pass:{ks_pass}",
                "--key-pass", f"pass:{ks_pass}",
                "--out", output_apk,
                unaligned_apk,
            ],
            capture_output=True,
            text=True,
        )
        if res_sign.returncode != 0:
            raise RuntimeError(f"Apksigner sign failed: {res_sign.stderr}")

        return output_apk
