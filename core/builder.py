#!/usr/bin/env python3
# [Builder]
# Android 图标包工程维护、资源同步与一键打包签名服务

import os
import shutil
import subprocess

# [Constants]
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANDROID_DIR = os.path.join(PROJECT_DIR, "android")
RES_DIR = os.path.join(ANDROID_DIR, "res")
ASSETS_DIR = os.path.join(ANDROID_DIR, "assets")
TOOLS_DIR = os.path.join(PROJECT_DIR, "tools")
BUILD_TMP_DIR = os.path.join(PROJECT_DIR, "build_tmp")

from core.env import AAPT2, ANDROID_JAR
APKSIGNER_JAR = os.path.join(TOOLS_DIR, "apksigner.jar")

KEYSTORE_PATH = os.path.join(TOOLS_DIR, "release.jks")
KEYSTORE_PASS = "materialyou"
KEY_ALIAS = "addon"

# [Service]
class ApkBuilder:
    def __init__(self):
        self.ensure_dirs()
        self.ensure_color_resources()

    def ensure_dirs(self):
        os.makedirs(os.path.join(RES_DIR, "drawable"), exist_ok=True)
        os.makedirs(os.path.join(RES_DIR, "drawable-anydpi-v26"), exist_ok=True)
        os.makedirs(os.path.join(RES_DIR, "drawable-anydpi-v33"), exist_ok=True)
        os.makedirs(os.path.join(RES_DIR, "values"), exist_ok=True)
        os.makedirs(os.path.join(RES_DIR, "values-night"), exist_ok=True)
        os.makedirs(os.path.join(RES_DIR, "values-v31"), exist_ok=True)
        os.makedirs(os.path.join(RES_DIR, "values-night-v31"), exist_ok=True)
        os.makedirs(ASSETS_DIR, exist_ok=True)
        os.makedirs(BUILD_TMP_DIR, exist_ok=True)

    def ensure_color_resources(self):
        """配置与原生 Material You (Android 12+) 及 PashaPuma 规范完全同源的动态色值"""
        # 1. values/colors.xml (通用浅色回退)
        with open(os.path.join(RES_DIR, "values", "colors.xml"), "w", encoding="utf-8") as f:
            f.write('''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="bg_themed_icons">#BAEAFF</color>
    <color name="fg_themed_icons">#004D62</color>
    <color name="ic_bg">#BAEAFF</color>
    <color name="ic_fg">#004D62</color>
    <color name="ic_bg_sky">#BAEAFF</color>
    <color name="ic_launcher_bg">#BAEAFF</color>
    <color name="ic_launcher_fg">#004D62</color>
    <color name="ic_launcher_mono">#FFFFFF</color>
</resources>
''')

        # 2. values-night/colors.xml (通用深色回退)
        with open(os.path.join(RES_DIR, "values-night", "colors.xml"), "w", encoding="utf-8") as f:
            f.write('''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="bg_themed_icons">#1D3138</color>
    <color name="fg_themed_icons">#BAEAFF</color>
    <color name="ic_bg">#1D3138</color>
    <color name="ic_fg">#BAEAFF</color>
</resources>
''')

        # 3. values-v31/colors.xml (Android 12+ 浅色 Monet 动态取色: 100% 匹配当前壁纸)
        with open(os.path.join(RES_DIR, "values-v31", "colors.xml"), "w", encoding="utf-8") as f:
            f.write('''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="bg_themed_icons">@android:color/system_accent1_100</color>
    <color name="fg_themed_icons">@android:color/system_accent1_700</color>
    <color name="ic_bg">@android:color/system_accent1_100</color>
    <color name="ic_fg">@android:color/system_accent1_700</color>
</resources>
''')

        # 4. values-night-v31/colors.xml (Android 12+ 深色 Monet 动态取色: 100% 匹配 PashaPuma 与深色壁纸)
        with open(os.path.join(RES_DIR, "values-night-v31", "colors.xml"), "w", encoding="utf-8") as f:
            f.write('''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="bg_themed_icons">@android:color/system_accent2_800</color>
    <color name="fg_themed_icons">@android:color/system_accent1_200</color>
    <color name="ic_bg">@android:color/system_accent2_800</color>
    <color name="ic_fg">@android:color/system_accent1_200</color>
</resources>
''')

    def clean_icons(self):
        """
        清空除基础 pack logo 以外的所有应用图标资源
        """
        for d in ["drawable", "drawable-anydpi-v26", "drawable-anydpi-v33"]:
            target_dir = os.path.join(RES_DIR, d)
            if not os.path.exists(target_dir):
                continue
            for item in os.listdir(target_dir):
                if not item.startswith("ic_pack_logo"):
                    path = os.path.join(target_dir, item)
                    if os.path.isfile(path) or os.path.islink(path):
                        os.remove(path)
                    elif os.path.isdir(path):
                        shutil.rmtree(path)
        self.ensure_color_resources()
        self.write_appfilter([])

    def add_icon_resource(self, drawable_name, full_png, fg_png, mono_png):
        """
        注册单个图标资源及其自适应/动态取色 XML，严格分离入口与前景/蒙版资源名，杜绝递归引用
        """
        # 1. 完整位图 (常规启动器直接引用)
        dest_full = os.path.join(RES_DIR, "drawable", f"{drawable_name}.png")
        shutil.copyfile(full_png, dest_full)

        # 2. 前景位图 (透明背景主体)
        dest_fg = os.path.join(RES_DIR, "drawable", f"{drawable_name}_fg.png")
        shutil.copyfile(fg_png, dest_fg)

        # 3. 动态取色蒙版 (纯白 Alpha 蒙版)
        dest_mono = os.path.join(RES_DIR, "drawable", f"{drawable_name}_mono.png")
        shutil.copyfile(mono_png, dest_mono)

        # 4. 自适应/动态着色图标 (使用系统动态色彩 Background + Foreground Tint + Monochrome)
        adaptive_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/bg_themed_icons" />
    <foreground>
        <bitmap
            android:src="@drawable/{drawable_name}_mono"
            android:tint="@color/fg_themed_icons" />
    </foreground>
    <monochrome android:drawable="@drawable/{drawable_name}_mono" />
</adaptive-icon>"""

        with open(os.path.join(RES_DIR, "drawable-anydpi-v26", f"{drawable_name}.xml"), "w", encoding="utf-8") as f:
            f.write(adaptive_xml)

        with open(os.path.join(RES_DIR, "drawable-anydpi-v33", f"{drawable_name}.xml"), "w", encoding="utf-8") as f:
            f.write(adaptive_xml)

    def write_appfilter(self, items):
        """
        生成标准的 appfilter.xml 和 drawable.xml 索引文件
        items: list of dict(pkg=..., activity=..., drawable=..., name=...)
        """
        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<resources>'
        ]

        drawable_lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<resources>',
            '    <version>1</version>',
            '    <category title="Addons" />'
        ]

        seen_drawables = set()

        for it in items:
            pkg = it['pkg']
            act = it['activity']
            drw = it['drawable']
            name = it.get('name', pkg)

            if drw not in seen_drawables:
                drawable_lines.append(f'    <item drawable="{drw}" />')
                seen_drawables.add(drw)

            comps = []
            # 1. 原始完整类名
            comps.append(f"{pkg}/{act}")

            # 2. 规范相对类名 (如 com.foo/com.foo.bar.Act -> com.foo/.bar.Act)
            if act.startswith(pkg):
                rel = act[len(pkg):]
                if not rel.startswith("."):
                    rel = "." + rel
                comps.append(f"{pkg}/{rel}")
            elif not act.startswith("."):
                comps.append(f"{pkg}/.{act}")

            # 3. 简写末尾名 (.MainActivity 等)
            comps.append(f"{pkg}/.{act.split('.')[-1]}")
            comps.append(f"{pkg}/{pkg}.MainActivity")
            comps.append(f"{pkg}/.MainActivity")

            # 4. 春秋检测全覆盖 (真机实际为 com.chunqiunativecheck/.SplashActivity)
            if "chunqiu" in pkg:
                for alt_p in ["com.chunqiunativecheck", "com.chunqiuativecheck", "com.chunqiu.nativecheck", "com.chunqiudetector"]:
                    for alt_a in [".SplashActivity", f"{alt_p}.SplashActivity", ".MainActivity", f"{alt_p}.MainActivity", ".ui.MainActivity"]:
                        comps.append(f"{alt_p}/{alt_a}")

            # 5. FuseHide 全覆盖 (真机实际为 io.github.xiaotong6666.fusehide/.ui.app.MainActivity)
            if "fusehide" in pkg:
                for alt_a in [
                    ".ui.app.MainActivity",
                    "io.github.xiaotong6666.fusehide.ui.app.MainActivity",
                    ".MainActivity",
                    "io.github.xiaotong6666.fusehide.MainActivity"
                ]:
                    comps.append(f"{pkg}/{alt_a}")

            # 6. 迅雷云盘全覆盖 (真机实际为 com.xunlei.downloadprovider.launch.LaunchActivity)
            if "tdmcloud" in pkg or "xunlei" in pkg:
                for alt_a in [
                    "com.xunlei.downloadprovider.launch.LaunchActivity",
                    ".launch.LaunchActivity",
                    ".MainActivity",
                    f"{pkg}.MainActivity",
                    ".launchDefault",
                    f"{pkg}.launchDefault"
                ]:
                    comps.append(f"{pkg}/{alt_a}")

            # 7. 2048 各种包名变体
            if "2048" in pkg:
                for alt_p in ["com.game2048", "com.estoty.2048", "com.estoty.game2048", "com.uberspot.a2048", "com.androbaby.original2048", "com.androbaby.game2048", "com.s2apps.game2048"]:
                    for alt_a in [".MainActivity", f"{alt_p}.MainActivity", f"{alt_p}.AppActivity", ".AppActivity"]:
                        comps.append(f"{alt_p}/{alt_a}")

            # 8. Box 变体
            if "box" in pkg:
                comps.append(f"{pkg}/.MainActivity")
                comps.append(f"{pkg}/com.box.app.MainActivity")

            # 9. 米窗 Freeform
            if "freeform" in pkg:
                for alt_a in [
                    ".ui.main.MainActivity",
                    "com.sunshine.freeform.ui.main.MainActivity",
                    ".activity.splash.SplashActivity",
                    "com.sunshine.freeform.activity.splash.SplashActivity",
                    ".MainActivity"
                ]:
                    comps.append(f"{pkg}/{alt_a}")

            # 10. 米窗侧边栏 Sidebar
            if "sidebar" in pkg:
                for alt_a in [
                    ".ui.main.MainActivity",
                    "io.sunshine0523.sidebar.ui.main.MainActivity",
                    ".MainActivity"
                ]:
                    comps.append(f"{pkg}/{alt_a}")

            # 11. SukiSU Ultra
            if "sukisu" in pkg:
                for alt_a in [
                    ".ui.MainActivity",
                    ".ui.MainActivityAlias",
                    "com.sukisu.ultra.ui.MainActivity",
                    "com.sukisu.ultra.ui.MainActivityAlias",
                    ".MainActivity"
                ]:
                    comps.append(f"{pkg}/{alt_a}")

            # 12. MiPush 管理器
            if "mipush" in pkg:
                for alt_a in [
                    ".app.MainActivityDefault",
                    "io.github.magisk317.mipush.app.MainActivityDefault",
                    ".MainActivity"
                ]:
                    comps.append(f"{pkg}/{alt_a}")

            # 13. The Past Within (Unity 引擎游戏)
            if "RustyLake" in pkg or "ThePastWithin" in pkg:
                for alt_a in [
                    "com.unity3d.player.UnityPlayerActivity",
                    ".UnityPlayerActivity",
                    ".MainActivity"
                ]:
                    comps.append(f"{pkg}/{alt_a}")

            # 去重按顺序写入
            added_for_this = set()
            for c in comps:
                if c not in added_for_this:
                    lines.append(f'    <item component="ComponentInfo{{{c}}}" drawable="{drw}" name="{name}" />')
                    added_for_this.add(c)

        lines.append('</resources>')
        drawable_lines.append('</resources>')

        appfilter_path = os.path.join(ASSETS_DIR, "appfilter.xml")
        with open(appfilter_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        drawable_path = os.path.join(ASSETS_DIR, "drawable.xml")
        with open(drawable_path, "w", encoding="utf-8") as f:
            f.write("\n".join(drawable_lines) + "\n")

    def build_apk(self, output_apk):
        """
        执行 aapt2 编译、资源链接及 apksigner 签名
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_apk)), exist_ok=True)
        compiled_zip = os.path.join(BUILD_TMP_DIR, "compiled.zip")
        unaligned_apk = os.path.join(BUILD_TMP_DIR, "unaligned.apk")

        # 1. aapt2 compile
        cmd_compile = [AAPT2, "compile", "--dir", RES_DIR, "-o", compiled_zip]
        res_compile = subprocess.run(cmd_compile, capture_output=True, text=True)
        if res_compile.returncode != 0:
            raise RuntimeError(f"AAPT2 compile failed: {res_compile.stderr}")

        # 2. aapt2 link
        cmd_link = [
            AAPT2, "link",
            "-I", ANDROID_JAR,
            "-A", ASSETS_DIR,
            "--manifest", os.path.join(ANDROID_DIR, "AndroidManifest.xml"),
            "--auto-add-overlay",
            "-o", unaligned_apk,
            compiled_zip
        ]
        res_link = subprocess.run(cmd_link, capture_output=True, text=True)
        if res_link.returncode != 0:
            raise RuntimeError(f"AAPT2 link failed: {res_link.stderr}")

        # 3. apksigner
        cmd_sign = [
            "java", "-jar", APKSIGNER_JAR, "sign",
            "--ks", KEYSTORE_PATH,
            "--ks-key-alias", KEY_ALIAS,
            "--ks-pass", f"pass:{KEYSTORE_PASS}",
            "--key-pass", f"pass:{KEYSTORE_PASS}",
            "--out", output_apk,
            unaligned_apk
        ]
        res_sign = subprocess.run(cmd_sign, capture_output=True, text=True)
        if res_sign.returncode != 0:
            raise RuntimeError(f"Apksigner sign failed: {res_sign.stderr}")

        return output_apk
