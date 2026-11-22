#!/usr/bin/env python3
# [Resolver]
# Android 应用组件识别、模糊容错匹配与声明式动态包名探测

import difflib
import json
import os
import re

from core.adb import AdbClient
from core.config import COMPONENTS_FILE, load_pack_config


# [Service]
class AppResolver:
    def __init__(self, device_id=None, adb=None):
        self.adb = adb or AdbClient(device_id)
        self.device_id = self.adb.device_id
        self.components = {}
        if os.path.exists(COMPONENTS_FILE):
            with open(COMPONENTS_FILE, "r", encoding="utf-8") as f:
                self.components = json.load(f)

    def resolve(self, pkg_or_name):
        """
        根据包名或应用名称，自动解析标准 ComponentInfo 映射
        返回: (package_name, activity_name, display_name)
        """
        pkg_or_name = pkg_or_name.strip()

        # 1. 精确匹配本地组件库
        if pkg_or_name in self.components:
            info = self.components[pkg_or_name]
            return pkg_or_name, info["activity"], info.get("name", pkg_or_name)

        # 2. 若已连接 ADB，从真机实时解析
        adb_result = self._query_adb(pkg_or_name)
        if adb_result:
            return adb_result

        # 3. 本地名称模糊匹配
        for pkg, info in self.components.items():
            if pkg_or_name.lower() in info.get("name", "").lower():
                return pkg, info["activity"], info.get("name", pkg)

        # 4. 无法命中时回退标准入口推测
        clean_pkg = re.sub(r"[^a-zA-Z0-9._]", "", pkg_or_name)
        return clean_pkg, f"{clean_pkg}.MainActivity", clean_pkg

    def _resolve_activity_on_device(self, pkg):
        res = self.adb.run("shell", "cmd", "package", "resolve-activity", "--brief", pkg, timeout=2, check=False)
        if res.returncode != 0:
            return None
        lines = [line.strip() for line in res.stdout.splitlines() if "/" in line]
        if not lines:
            return None
        match = re.match(r"([^/]+)/(.+)", lines[-1])
        if not match:
            return None
        p, a = match.groups()
        if a.startswith("."):
            a = p + a
        return p, a, p

    def _query_adb(self, query):
        if not self.device_id:
            return None
        try:
            direct = self._resolve_activity_on_device(query)
            if direct:
                return direct

            res_pm = self.adb.run("shell", "pm", "list", "packages", timeout=3, check=False)
            if res_pm.returncode != 0:
                return None
            pkgs = [
                line.split(":")[-1].strip()
                for line in res_pm.stdout.splitlines()
                if line.startswith("package:")
            ]
            matches = difflib.get_close_matches(query, pkgs, n=1, cutoff=0.5)
            if not matches:
                q_lower = query.lower()
                matches = [p for p in pkgs if any(w in p.lower() for w in q_lower.split(".") if len(w) >= 4)]
            if matches:
                return self._resolve_activity_on_device(matches[0])
        except Exception:
            pass
        return None

    def detect_dynamic_apps(self, rules=None):
        """
        根据 pack.json 的 dynamic_apps 声明探测真机随机包名应用 (如 SukiSU Ultra)
        返回临时 manifest 兼容映射列表，不写入持久化 manifest.json
        """
        if not self.device_id:
            return []
        if rules is None:
            rules = load_pack_config().get("dynamic_apps", [])

        items = []
        seen = set()
        for rule in rules:
            action = rule.get("intent_action", "android.intent.action.VIEW")
            data_uri = rule.get("intent_data")
            drawable = rule.get("drawable")
            name = rule.get("name", drawable)
            include_alias = rule.get("include_alias_suffix", False)
            if not data_uri or not drawable:
                continue
            try:
                out = self.adb.shell(
                    "cmd", "package", "query-activities", "--brief", "-a", action, "-d", data_uri,
                    timeout=3,
                )
            except Exception:
                continue

            found_pkgs = set()
            for line in out.splitlines():
                line = line.strip()
                if "/" not in line or line.startswith("Activity") or line.startswith("priority"):
                    continue
                pkg, act = line.split("/", 1)
                if act.startswith("."):
                    act = pkg + act
                found_pkgs.add(pkg)
                self._append_dynamic_item(items, seen, pkg, act, name, drawable, include_alias)

            for pkg in found_pkgs:
                resolved = self._resolve_activity_on_device(pkg)
                if resolved:
                    self._append_dynamic_item(items, seen, resolved[0], resolved[1], name, drawable, include_alias)
        return items

    @staticmethod
    def _append_dynamic_item(items, seen, pkg, act, name, drawable, include_alias):
        if (pkg, act, drawable) not in seen:
            seen.add((pkg, act, drawable))
            items.append({"pkg": pkg, "activity": act, "name": name, "drawable": drawable})
        if include_alias and not act.endswith("Alias"):
            alias_act = act + "Alias"
            if (pkg, alias_act, drawable) not in seen:
                seen.add((pkg, alias_act, drawable))
                items.append({"pkg": pkg, "activity": alias_act, "name": name, "drawable": drawable})

    @staticmethod
    def get_drawable_name(pkg):
        clean = re.sub(r"[^a-zA-Z0-9]", "_", pkg).lower()
        clean = re.sub(r"_+", "_", clean).strip("_")
        return f"ic_{clean}"
