#!/usr/bin/env python3
# [Config]
# 项目路径常量、pack.json 配置与 manifest.json 读写入口

import json
import os

# [Paths]
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK_CONFIG_FILE = os.path.join(ROOT_DIR, "pack.json")
DATA_DIR = os.path.join(ROOT_DIR, "data")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
ANDROID_DIR = os.path.join(ROOT_DIR, "android")
ANDROID_RES_DIR = os.path.join(ANDROID_DIR, "res")
ANDROID_ASSETS_DIR = os.path.join(ANDROID_DIR, "assets")
TOOLS_DIR = os.path.join(ROOT_DIR, "tools")
BUILD_TMP_DIR = os.path.join(ROOT_DIR, "build_tmp")
MANIFEST_FILE = os.path.join(DATA_DIR, "manifest.json")
COMPONENTS_FILE = os.path.join(DATA_DIR, "components.json")

# [Defaults]
VALID_STYLES = ("monet", "adaptive", "bitmap")

DEFAULT_PACK_CONFIG = {
    "name": "MonetCraft",
    "label": "Pix Material You Addon",
    "package_name": "com.materialyou.honorofkings.addon",
    "version_code": 1,
    "version_name": "1.0",
    "style": "monet",
    "icon_size": 512,
    "apk_output": "output/MaterialYou_Addon.apk",
    "palette": {
        "light_bg": "#BAEAFF",
        "light_fg": "#004D62",
        "light_fg_sec": "#416D7D",
        "dark_bg": "#1D3138",
        "dark_fg": "#BAEAFF",
        "dark_fg_sec": "#7595A3",
    },
    "signing": {
        "keystore": "tools/release.jks",
        "alias": "addon",
        "password_env": "MONETCRAFT_KS_PASS",
        "default_password": "materialyou",
    },
    "host_gip_package": "com.richardluo.globalIconPack",
    "gip_db_path": "/data/misc/com.richardluo.globalIconPack/iconPack.db",
    "launcher_package": "com.google.android.apps.nexuslauncher",
    "dynamic_apps": [],
    "visual_center_overrides": {},
}


# [Loaders]
def resolve_path(rel_or_abs):
    if os.path.isabs(rel_or_abs):
        return rel_or_abs
    return os.path.join(ROOT_DIR, rel_or_abs)


def load_pack_config():
    cfg = dict(DEFAULT_PACK_CONFIG)
    if os.path.exists(PACK_CONFIG_FILE):
        with open(PACK_CONFIG_FILE, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        cfg.update(user_cfg)
        for nested in ("signing", "palette"):
            if nested in user_cfg:
                merged = dict(DEFAULT_PACK_CONFIG[nested])
                merged.update(user_cfg[nested])
                cfg[nested] = merged
    return cfg


def get_apk_output_path(cfg=None):
    cfg = cfg or load_pack_config()
    return resolve_path(cfg.get("apk_output", "output/MaterialYou_Addon.apk"))


def load_manifest():
    if os.path.exists(MANIFEST_FILE):
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_manifest(items):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
        f.write("\n")
