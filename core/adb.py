#!/usr/bin/env python3
# [ADB]
# 统一 ADB 通信、多设备嗅探与零残留临时文件封装

import os
import subprocess
import tempfile

from core.config import load_pack_config


# [Client]
class AdbClient:
    def __init__(self, device_id=None, gip_package=None):
        cfg = load_pack_config()
        self.gip_package = gip_package or cfg.get("host_gip_package", "com.richardluo.globalIconPack")
        self.device_id = device_id or self.detect_device(self.gip_package)

    @staticmethod
    def detect_device(preferred_pkg="com.richardluo.globalIconPack"):
        try:
            out = subprocess.check_output(["adb", "devices"], timeout=3).decode("utf-8")
        except Exception:
            return None
        devices = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        if not devices:
            return None
        if len(devices) == 1:
            return devices[0]
        for dev in devices:
            try:
                res = subprocess.run(
                    ["adb", "-s", dev, "shell", f"pm path {preferred_pkg}"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if "package:" in res.stdout:
                    return dev
            except Exception:
                pass
        return devices[0]

    def ensure_connected(self):
        if not self.device_id:
            raise RuntimeError("未检测到已连接的 ADB 设备")
        return self.device_id

    def base_cmd(self):
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        return cmd

    def run(self, *args, timeout=None, check=True):
        cmd = self.base_cmd() + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check)

    def output(self, *args, timeout=None):
        cmd = self.base_cmd() + list(args)
        return subprocess.check_output(cmd, timeout=timeout).decode("utf-8", errors="ignore")

    def shell(self, *args, timeout=None):
        return self.output("shell", *args, timeout=timeout)

    def root(self, command, timeout=None):
        return self.output("shell", f"su -c '{command}'", timeout=timeout)

    def pull_root_file(self, remote_path, local_path=None):
        """通过 /data/local/tmp 中转拉取 root 文件，并确保远端临时副本立即清理"""
        self.ensure_connected()
        tmp_remote = f"/data/local/tmp/mc_pull_{os.getpid()}.tmp"
        target_local = local_path or tempfile.mktemp(prefix="mc_", suffix=".tmp")
        try:
            self.root(f"cp {remote_path} {tmp_remote} && chmod 644 {tmp_remote}")
            self.run("pull", tmp_remote, target_local)
        finally:
            self.run("shell", f"su -c 'rm -f {tmp_remote}'", check=False)
        return target_local

    def screencap_bytes(self):
        """直接经由 stdout 管道截取屏幕，严禁在 /sdcard/ 留下文件"""
        self.ensure_connected()
        return subprocess.check_output(self.base_cmd() + ["exec-out", "screencap", "-p"])
