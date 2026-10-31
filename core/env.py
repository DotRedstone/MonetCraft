#!/usr/bin/env python3
# [Env]
# 运行环境与工具链动态探测与自适应解析器

import os
import shutil

import subprocess

def test_executable(cmd):
    if not cmd:
        return False
    try:
        res = subprocess.run([cmd, "version"], capture_output=True, timeout=2)
        return res.returncode == 0
    except Exception:
        return False

def find_tool(name, alt_name=None, nix_fallback=None):
    """
    优先从系统 PATH 查找命令，支持备用名及 NixOS 路径兜底
    """
    found = shutil.which(name)
    if found:
        return found
    if alt_name:
        found_alt = shutil.which(alt_name)
        if found_alt:
            return found_alt
    if nix_fallback and os.path.exists(nix_fallback):
        return nix_fallback
    return name

def find_aapt2():
    """
    查找可执行的 aapt2 二进制文件：
    1. PATH
    2. $ANDROID_HOME / $ANDROID_SDK_ROOT / build-tools
    3. ~/Android/Sdk/build-tools
    4. NixOS 兜底路径
    """
    found = shutil.which("aapt2")
    if found and test_executable(found):
        return found

    sdk_dirs = []
    for env in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
        val = os.environ.get(env)
        if val and os.path.exists(val):
            sdk_dirs.append(val)
    sdk_dirs.append(os.path.expanduser("~/Android/Sdk"))

    for sdk in sdk_dirs:
        bt_dir = os.path.join(sdk, "build-tools")
        if os.path.exists(bt_dir):
            try:
                versions = sorted(os.listdir(bt_dir), reverse=True)
                for v in versions:
                    candidate = os.path.join(bt_dir, v, "aapt2")
                    if os.path.exists(candidate) and os.access(candidate, os.X_OK) and test_executable(candidate):
                        return candidate
            except Exception:
                pass

    nix_fallback = "/nix/store/6crxa247jcvlj28klg6c6mdjmv51anwk-aapt-8.13.2-14304508/bin/aapt2"
    if os.path.exists(nix_fallback) and test_executable(nix_fallback):
        return nix_fallback

    return "aapt2"

def find_android_jar():
    """
    查找 android.jar 平台框架存根库：
    1. $ANDROID_JAR
    2. $ANDROID_HOME / $ANDROID_SDK_ROOT / platforms
    3. ~/Android/Sdk/platforms
    4. 兜底回退
    """
    env_jar = os.environ.get("ANDROID_JAR")
    if env_jar and os.path.exists(env_jar):
        return env_jar

    sdk_dirs = []
    for env in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
        val = os.environ.get(env)
        if val and os.path.exists(val):
            sdk_dirs.append(val)
    sdk_dirs.append(os.path.expanduser("~/Android/Sdk"))

    for sdk in sdk_dirs:
        plat_dir = os.path.join(sdk, "platforms")
        if os.path.exists(plat_dir):
            try:
                plats = sorted(os.listdir(plat_dir), reverse=True)
                for p in plats:
                    candidate = os.path.join(plat_dir, p, "android.jar")
                    if os.path.exists(candidate):
                        return candidate
            except Exception:
                pass

    return "android.jar"

# [Constants]
CONVERT = find_tool("magick", alt_name="convert", nix_fallback="/nix/store/hpfmkrj5xl7v5ndwq4r76gn99cxfxhp3-imagemagick-7.1.2-24/bin/convert")
POTRACE = find_tool("potrace", nix_fallback="/nix/store/45iabzr7g9xpxyx6vqp7zgibl81v04ac-potrace-1.16/bin/potrace")
RESVG = find_tool("resvg", nix_fallback="/nix/store/31dqi84g55pm02y0p375khrcd4dqdbzi-resvg-0.47.0/bin/resvg")
AAPT2 = find_aapt2()
ANDROID_JAR = find_android_jar()
