#!/usr/bin/env python3
# [Deployer]
# 自动部署 APK、同步 Global Icon Pack 数据库并刷新桌面图标缓存

import os
import re
import sqlite3
import struct
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

from core.adb import AdbClient
from core.config import get_apk_output_path, load_pack_config
from core.env import AAPT2
from core.resolver import AppResolver


# [Service]
class IconDeployer:
    def __init__(self, device_id=None, pack_config=None, adb=None):
        self.cfg = pack_config or load_pack_config()
        self.adb = adb or AdbClient(device_id, gip_package=self.cfg["host_gip_package"])
        self.device_id = self.adb.device_id
        self.apk_path = get_apk_output_path(self.cfg)
        self.addon_pack_name = self.cfg["package_name"]
        self.gip_pkg = self.cfg["host_gip_package"]
        self.gip_db_path = self.cfg["gip_db_path"]
        self.launcher_pkg = self.cfg["launcher_package"]

    def install_apk(self, apk_path=None):
        self.adb.ensure_connected()
        target = apk_path or self.apk_path
        print(f"📦 正在安装 APK 到设备 {self.device_id}...")
        out = self.adb.output("install", "-r", target)
        print("   " + out.strip())

    def get_resource_ids(self, apk_path=None):
        target = apk_path or self.apk_path
        out = subprocess.check_output([AAPT2, "dump", "resources", target]).decode("utf-8")
        res_map = {}
        for line in out.splitlines():
            m = re.search(r"resource (0x7f[0-9a-f]+) drawable/(\w+)", line)
            if m:
                res_map[m.group(2)] = int(m.group(1), 16)
        return res_map

    def parse_apk_mappings(self, res_map, apk_path=None):
        """直接读取已构建 APK 内的 assets/appfilter.xml，确保与 PLEnhanced 读取内容完全一致"""
        target = apk_path or self.apk_path
        with zipfile.ZipFile(target, "r") as zf:
            xml_bytes = zf.read("assets/appfilter.xml")
        root = ET.fromstring(xml_bytes)
        mappings = set()
        for item in root.findall("item"):
            comp = item.get("component") or ""
            drawable = item.get("drawable") or ""
            m = re.match(r"ComponentInfo\{([^/]+)/([^}]+)\}", comp)
            if m and drawable in res_map:
                pkg, act = m.group(1), m.group(2)
                if act.startswith("."):
                    act = pkg + act
                mappings.add((pkg, act, drawable))
                mappings.add((pkg, "", drawable))
        return mappings

    def _collect_dynamic_mappings(self, res_map):
        resolver = AppResolver(self.device_id, adb=self.adb)
        dynamic_items = resolver.detect_dynamic_apps(self.cfg.get("dynamic_apps", []))
        mappings = set()
        reported_pkgs = set()
        for it in dynamic_items:
            drw = it["drawable"]
            if drw not in res_map:
                continue
            pkg, act = it["pkg"], it["activity"]
            if act.startswith("."):
                act = pkg + act
            mappings.add((pkg, act, drw))
            mappings.add((pkg, "", drw))
            if pkg not in reported_pkgs:
                print(f"   🎯 动态捕获 {it['name']} 随机包名: {pkg}")
                reported_pkgs.add(pkg)
        return mappings

    def sync_global_icon_pack(self, apk_path=None):
        self.adb.ensure_connected()
        target_apk = apk_path or self.apk_path
        local_tmp = tempfile.mktemp(prefix="mc_gip_", suffix=".db")
        remote_push = f"/data/local/tmp/mc_push_{os.getpid()}.db"

        print("🔄 正在提取设备上的全局图标包数据库...")
        try:
            self.adb.root(f"am force-stop {self.gip_pkg}")
            self.adb.root(f"cp {self.gip_db_path} {self.gip_db_path}.bak")
            self.adb.pull_root_file(self.gip_db_path, local_tmp)

            res_map = self.get_resource_ids(target_apk)
            mappings = self.parse_apk_mappings(res_map, target_apk)
            mappings |= self._collect_dynamic_mappings(res_map)
            print(f"   已解析 {len(mappings)} 条组件映射 (匹配资源 ID)")

            conn = sqlite3.connect(local_tmp)
            c = conn.cursor()

            base_packs = [
                r[0]
                for r in c.execute("SELECT pack FROM iconPack WHERE pack != ?", (self.addon_pack_name,)).fetchall()
            ]
            print(f"   检测到宿主主题包: {base_packs}")

            addon_table = f"pack/{self.addon_pack_name}"
            c.execute(f"""
            CREATE TABLE IF NOT EXISTS "{addon_table}" (
                packageName TEXT NOT NULL,
                className TEXT NOT NULL,
                entry BLOB NOT NULL,
                pack TEXT NOT NULL DEFAULT "",
                id INTEGER NOT NULL DEFAULT 0
            )
            """)
            c.execute(f'DELETE FROM "{addon_table}"')

            addon_pkgs = {pkg for pkg, _, _ in mappings}
            for bp in base_packs:
                bp_table = f"pack/{bp}"
                c.execute(f'DELETE FROM "{bp_table}" WHERE pack=?', (self.addon_pack_name,))
                for pkg in addon_pkgs:
                    c.execute(f'DELETE FROM "{bp_table}" WHERE packageName=?', (pkg,))

            for pkg, act, drawable in mappings:
                res_id = res_map[drawable]
                entry_blob = b"\x00" + struct.pack(">H", len(drawable)) + drawable.encode("utf-8")
                c.execute(f'INSERT INTO "{addon_table}" VALUES (?, ?, ?, ?, ?)', (pkg, act, entry_blob, "", res_id))
                for bp in base_packs:
                    bp_table = f"pack/{bp}"
                    c.execute(
                        f'INSERT INTO "{bp_table}" VALUES (?, ?, ?, ?, ?)',
                        (pkg, act, entry_blob, self.addon_pack_name, res_id),
                    )

            now = int(time.time() * 1000)
            for bp in base_packs:
                c.execute("UPDATE iconPack SET updateAt=?, modified=1 WHERE pack=?", (now, bp))
            c.execute("UPDATE iconPack SET updateAt=? WHERE pack=?", (now, self.addon_pack_name))

            conn.commit()
            conn.close()

            print("🚀 正在将最新数据库推送回设备...")
            self.adb.run("push", local_tmp, remote_push)
            self.adb.root(
                f"cp {remote_push} {self.gip_db_path} && chmod 666 {self.gip_db_path} && chown nobody:nobody {self.gip_db_path}"
            )
            self.adb.root(f"cp {remote_push} {self.gip_db_path}.bak")

            print("🧹 正在清理 Pixel Launcher 图标缓存并重启桌面...")
            self.adb.root(f"rm -f /data/data/{self.launcher_pkg}/databases/app_icons.db*")
            self.adb.root(f"killall {self.launcher_pkg}")
            self.adb.root(f"am force-stop {self.gip_pkg}")
        finally:
            self.adb.run("shell", f"su -c 'rm -f {remote_push}'", check=False)
            if os.path.exists(local_tmp):
                os.remove(local_tmp)

        print("✨ 同步完成！全量图标已即时生效。")

    def deploy_all(self, apk_path=None):
        self.install_apk(apk_path)
        self.sync_global_icon_pack(apk_path)
