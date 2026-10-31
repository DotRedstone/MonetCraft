#!/usr/bin/env python3
# [Deployer]
# 自动部署 APK、同步 Global Icon Pack 数据库并刷新桌面图标缓存

import os
import re
import sqlite3
import struct
import subprocess
import time
import xml.etree.ElementTree as ET

# [Constants]
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APK_PATH = os.path.join(PROJECT_DIR, "output", "MaterialYou_Addon.apk")
APPFILTER_PATH = os.path.join(PROJECT_DIR, "android", "assets", "appfilter.xml")
from core.env import AAPT2
DB_REMOTE_PATH = "/data/misc/com.richardluo.globalIconPack/iconPack.db"
DB_LOCAL_TMP = "/tmp/iconPack_sync.db"
ADDON_PACK_NAME = "com.materialyou.honorofkings.addon"

class IconDeployer:
    def __init__(self, device_id=None):
        self.device_id = device_id or self._detect_device()

    def _detect_device(self):
        cmd = ["adb", "devices"]
        out = subprocess.check_output(cmd).decode("utf-8")
        lines = [line.strip() for line in out.splitlines() if line.strip() and not line.startswith("List of devices")]
        devices = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        if not devices:
            return None
        if len(devices) == 1:
            return devices[0]
        # 当有多台设备时，优先检测装有 Global Icon Pack 的目标机
        for dev in devices:
            try:
                res = subprocess.run(["adb", "-s", dev, "shell", "pm path com.richardluo.globalIconPack"], capture_output=True, text=True, timeout=2)
                if "package:" in res.stdout:
                    return dev
            except Exception:
                pass
        return devices[0]

    def _adb(self, *args):
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(args)
        return subprocess.check_output(cmd).decode("utf-8")

    def _adb_root(self, command):
        return self._adb("shell", f"su -c '{command}'")

    def install_apk(self, apk_path=APK_PATH):
        if not self.device_id:
            raise RuntimeError("未检测到已连接的 ADB 设备")
        print(f"📦 正在安装 APK 到设备 {self.device_id}...")
        res = self._adb("install", "-r", apk_path)
        print("   " + res.strip())

    def get_resource_ids(self, apk_path=APK_PATH):
        out = subprocess.check_output([AAPT2, "dump", "resources", apk_path]).decode("utf-8")
        res_map = {}
        for line in out.splitlines():
            m = re.search(r"resource (0x7f[0-9a-f]+) drawable/(\w+)", line)
            if m:
                res_map[m.group(2)] = int(m.group(1), 16)
        return res_map

    def parse_mappings(self, res_map):
        tree = ET.parse(APPFILTER_PATH)
        root = tree.getroot()
        mappings = set()
        for item in root.findall("item"):
            comp = item.get("component")
            drawable = item.get("drawable")
            m = re.match(r"ComponentInfo\{([^/]+)/([^}]+)\}", comp)
            if m and drawable in res_map:
                pkg = m.group(1)
                act = m.group(2)
                if act.startswith("."):
                    act = pkg + act
                mappings.add((pkg, act, drawable))
                mappings.add((pkg, "", drawable))
        return mappings

    def sync_global_icon_pack(self):
        if not self.device_id:
            raise RuntimeError("未检测到已连接的 ADB 设备")

        print("🔄 正在提取设备上的全局图标包数据库...")
        # 1. 杀掉常驻 GIP 进程，防止进程持有 SQLite 句柄导致并发写入被脏缓存冲刷
        self._adb_root("am force-stop com.richardluo.globalIconPack")
        self._adb_root(f"cp {DB_REMOTE_PATH} {DB_REMOTE_PATH}.bak")
        self._adb_root(f"cp {DB_REMOTE_PATH} /data/local/tmp/remote_gip.db && chmod 666 /data/local/tmp/remote_gip.db")
        subprocess.check_call(["adb", "-s", self.device_id, "pull", "/data/local/tmp/remote_gip.db", DB_LOCAL_TMP])
        self._adb_root("rm -f /data/local/tmp/remote_gip.db")

        res_map = self.get_resource_ids()
        mappings = self.parse_mappings(res_map)
        print(f"   已解析 {len(mappings)} 条组件映射 (匹配资源 ID)")

        conn = sqlite3.connect(DB_LOCAL_TMP)
        c = conn.cursor()

        # 检查活跃主图标包（如 PashaPuma）
        base_packs = [r[0] for r in c.execute("SELECT pack FROM iconPack WHERE pack != ?", (ADDON_PACK_NAME,)).fetchall()]
        print(f"   检测到宿主主题包: {base_packs}")

        # 确保补丁包独立数据表
        addon_table = f"pack/{ADDON_PACK_NAME}"
        c.execute(f"""
        CREATE TABLE IF NOT EXISTS "{addon_table}" (
            packageName TEXT NOT NULL,
            className TEXT NOT NULL,
            entry BLOB NOT NULL,
            pack TEXT NOT NULL DEFAULT "",
            id INTEGER NOT NULL DEFAULT 0
        )
        """)
        c.execute(f"DELETE FROM \"{addon_table}\"")

        # 同步各宿主包中的旧映射
        for bp in base_packs:
            bp_table = f"pack/{bp}"
            c.execute(f"DELETE FROM \"{bp_table}\" WHERE pack=\"{ADDON_PACK_NAME}\"")
            addon_pkgs = set(pkg for pkg, _, _ in mappings)
            for pkg in addon_pkgs:
                c.execute(f"DELETE FROM \"{bp_table}\" WHERE packageName=?", (pkg,))

        # 写入映射
        for pkg, act, drawable in mappings:
            res_id = res_map[drawable]
            entry_blob = b"\x00" + struct.pack(">H", len(drawable)) + drawable.encode("utf-8")
            c.execute(f"INSERT INTO \"{addon_table}\" VALUES (?, ?, ?, ?, ?)",
                      (pkg, act, entry_blob, "", res_id))
            for bp in base_packs:
                bp_table = f"pack/{bp}"
                c.execute(f"INSERT INTO \"{bp_table}\" VALUES (?, ?, ?, ?, ?)",
                          (pkg, act, entry_blob, ADDON_PACK_NAME, res_id))

        now = int(time.time() * 1000)
        for bp in base_packs:
            c.execute("UPDATE iconPack SET updateAt=?, modified=1 WHERE pack=?", (now, bp))
        c.execute("UPDATE iconPack SET updateAt=? WHERE pack=?", (now, ADDON_PACK_NAME))

        conn.commit()
        conn.close()

        print("🚀 正在将最新数据库推送回设备...")
        self._adb("push", DB_LOCAL_TMP, "/data/local/tmp/iconPack.db")
        self._adb_root(f"cp /data/local/tmp/iconPack.db {DB_REMOTE_PATH} && chmod 666 {DB_REMOTE_PATH} && chown nobody:nobody {DB_REMOTE_PATH}")
        self._adb_root(f"cp /data/local/tmp/iconPack.db {DB_REMOTE_PATH}.bak")

        print("🧹 正在清理 Pixel Launcher 图标缓存并重启桌面...")
        self._adb_root("rm -f /data/data/com.google.android.apps.nexuslauncher/databases/app_icons.db*")
        self._adb_root("killall com.google.android.apps.nexuslauncher")
        self._adb_root("am force-stop com.richardluo.globalIconPack")

        # 清理设备与本地临时文件
        self._adb_root("rm -f /data/local/tmp/iconPack.db /data/local/tmp/remote_gip.db")
        if os.path.exists(DB_LOCAL_TMP):
            os.remove(DB_LOCAL_TMP)

        print("✨ 同步完成！全量图标已即时生效。")

    def deploy_all(self):
        self.install_apk()
        self.sync_global_icon_pack()
