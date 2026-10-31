#!/usr/bin/env python3
# [Resolver]
# Android 应用组件识别与自动匹配服务

import difflib
import json
import os
import re
import subprocess

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "components.json")

class AppResolver:
    def __init__(self, device_id=None):
        self.device_id = device_id or self._detect_device()
        self.components = {}
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                self.components = json.load(f)

    def _detect_device(self):
        try:
            cmd = ["adb", "devices"]
            out = subprocess.check_output(cmd, timeout=2).decode("utf-8")
            devices = [line.split()[0] for line in out.splitlines() if line.strip() and not line.startswith("List of devices") and len(line.split()) >= 2 and line.split()[1] == "device"]
            if not devices:
                return None
            if len(devices) == 1:
                return devices[0]
            for dev in devices:
                res = subprocess.run(["adb", "-s", dev, "shell", "pm path com.richardluo.globalIconPack"], capture_output=True, text=True, timeout=2)
                if "package:" in res.stdout:
                    return dev
            return devices[0]
        except Exception:
            return None

    def resolve(self, pkg_or_name):
        """
        根据包名或应用名称，自动解析出标准的 ComponentInfo 映射
        返回: (package_name, activity_name, display_name)
        """
        pkg_or_name = pkg_or_name.strip()
        
        # 1. 精确匹配包名
        if pkg_or_name in self.components:
            info = self.components[pkg_or_name]
            return pkg_or_name, info["activity"], info.get("name", pkg_or_name)

        # 2. 如果已连接 ADB，尝试从手机直接查询
        adb_result = self._query_adb(pkg_or_name)
        if adb_result:
            return adb_result

        # 3. 模糊匹配名称
        for pkg, info in self.components.items():
            if pkg_or_name.lower() in info.get("name", "").lower():
                return pkg, info["activity"], info.get("name", pkg)

        # 4. 无法命中时，回退生成标准的入口推测
        clean_pkg = re.sub(r'[^a-zA-Z0-9._]', '', pkg_or_name)
        guessed_act = f"{clean_pkg}.MainActivity"
        return clean_pkg, guessed_act, clean_pkg

    def _query_adb(self, query):
        try:
            base_cmd = ["adb"]
            if self.device_id:
                base_cmd.extend(["-s", self.device_id])

            # 1. 直接尝试 resolve-activity
            cmd = base_cmd + ["shell", "cmd", "package", "resolve-activity", "--brief", query]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                lines = [l.strip() for l in res.stdout.splitlines() if "/" in l]
                if lines:
                    match = re.match(r'([^/]+)/(.+)', lines[-1])
                    if match:
                        p, a = match.groups()
                        if a.startswith("."):
                            a = p + a
                        return p, a, p

            # 2. 匹配失败时，检索真机已安装包名进行智能容错 (如拼写错误 chunqiuativecheck -> com.chunqiunativecheck)
            cmd_pm = base_cmd + ["shell", "pm", "list", "packages"]
            res_pm = subprocess.run(cmd_pm, capture_output=True, text=True, timeout=2)
            if res_pm.returncode == 0:
                pkgs = [l.split(":")[-1].strip() for l in res_pm.stdout.splitlines() if l.startswith("package:")]
                matches = difflib.get_close_matches(query, pkgs, n=1, cutoff=0.5)
                if not matches:
                    # 尝试按关键字包含搜索
                    q_lower = query.lower()
                    matches = [p for p in pkgs if any(w in p.lower() for w in q_lower.split(".") if len(w) >= 4)]
                
                if matches:
                    target_pkg = matches[0]
                    cmd_res = base_cmd + ["shell", "cmd", "package", "resolve-activity", "--brief", target_pkg]
                    res_res = subprocess.run(cmd_res, capture_output=True, text=True, timeout=2)
                    if res_res.returncode == 0:
                        lines = [l.strip() for l in res_res.stdout.splitlines() if "/" in l]
                        if lines:
                            match = re.match(r'([^/]+)/(.+)', lines[-1])
                            if match:
                                p, a = match.groups()
                                if a.startswith("."):
                                    a = p + a
                                return p, a, p
        except Exception:
            pass
        return None

    @staticmethod
    def get_drawable_name(pkg):
        clean = re.sub(r'[^a-zA-Z0-9]', '_', pkg).lower()
        clean = re.sub(r'_+', '_', clean).strip('_')
        return f"ic_{clean}"
