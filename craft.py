#!/usr/bin/env python3
# [CLI]
# Material You 图标生成与 APK 一键打包工具

import argparse
import json
import os
import sys

from core.builder import ApkBuilder
from core.deployer import IconDeployer
from core.resolver import AppResolver
from core.vectorizer import IconVectorizer

# [Paths]
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "data")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
TMP_DIR = os.path.join(ROOT_DIR, "build_tmp", "vector_work")
MANIFEST_FILE = os.path.join(DATA_DIR, "manifest.json")
DEFAULT_APK_OUT = os.path.join(OUTPUT_DIR, "MaterialYou_Addon.apk")

# [Storage]
def load_manifest():
    if os.path.exists(MANIFEST_FILE):
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_manifest(items):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

# [Handlers]
def cmd_reset(args):
    """重置图标包工程，清空历史临时图标"""
    save_manifest([])
    builder = ApkBuilder()
    builder.clean_icons()
    apk_path = builder.build_apk(DEFAULT_APK_OUT)
    print("\n✅ 已清空重置图标工程！")
    print(f"📦 基础包已生成: {apk_path}")
    print("👉 随时可以直接发送新的图片与包名进行添加。\n")

def cmd_add(args):
    """处理单张图片与包名，一键完成矢量提取、配置与打包"""
    img_path = os.path.abspath(args.image)
    if not os.path.exists(img_path):
        print(f"❌ 找不到图片文件: {img_path}")
        sys.exit(1)

    resolver = AppResolver()
    pkg, act, default_name = resolver.resolve(args.package_or_name)
    display_name = args.name if args.name else default_name
    drawable_name = resolver.get_drawable_name(pkg)

    print(f"\n==========================================")
    print(f"🚀 开始处理应用: {display_name}")
    print(f"   包名: {pkg}")
    print(f"   活动: {act}")
    print(f"   标识: {drawable_name}")
    print(f"==========================================")

    # 1. 矢量提取与渲染
    print("\n[1/3] 正在提取矢量轮廓并生成 MD3 双色分层...")
    vectorizer = IconVectorizer(TMP_DIR)
    results = vectorizer.process(img_path, drawable_name, OUTPUT_DIR, ASSETS_DIR)

    # 2. 注入资源与清单维护
    print("[2/3] 注入 Android 资源与更新组件映射...")
    builder = ApkBuilder()
    builder.add_icon_resource(drawable_name, results["normal_png"], results["fg_png"], results["mono_png"])

    manifest = load_manifest()
    # 替换已有或追加新项
    manifest = [item for item in manifest if item["pkg"] != pkg]
    item_record = {
        "pkg": pkg,
        "activity": act,
        "name": display_name,
        "drawable": drawable_name,
        "normal_png": os.path.relpath(results["normal_png"], ROOT_DIR),
        "dark_png": os.path.relpath(results["dark_png"], ROOT_DIR),
        "fg_png": os.path.relpath(results["fg_png"], ROOT_DIR),
        "mono_png": os.path.relpath(results["mono_png"], ROOT_DIR)
    }
    manifest.append(item_record)
    save_manifest(manifest)
    builder.write_appfilter(manifest)

    # 3. 自动打包编译
    print("[3/3] 编译并签名最新 APK...")
    final_apk = builder.build_apk(DEFAULT_APK_OUT)

    print("\n🎉 处理并打包完成！")
    print(f"   📱 当前图标包收录应用总数: {len(manifest)}")
    print(f"   📦 最终安装包: {final_apk}")
    print(f"   🖼️ 浅色预览: {results['normal_png']}")
    print(f"   🌙 深色预览: {results['dark_png']}")
    print(f"   🎨 动态蒙版: {results['mono_png']}\n")

    if getattr(args, "deploy", False):
        device_id = getattr(args, "device", None)
        deployer = IconDeployer(device_id)
        deployer.deploy_all()

def cmd_list(args):
    """列出当前图标包收录的应用"""
    manifest = load_manifest()
    if not manifest:
        print("\n📭 当前图标包为空，尚未添加任何应用。")
        return

    print(f"\n📋 当前图标包包含 {len(manifest)} 个应用：")
    for i, it in enumerate(manifest, 1):
        print(f" {i}. [{it['name']}]")
        print(f"    包名: {it['pkg']}")
        print(f"    组件: {it['activity']}")
        print(f"    资源: {it['drawable']}")
        preview = it.get('normal_png', 'N/A')
        if preview != 'N/A' and not os.path.isabs(preview):
            preview = os.path.join(ROOT_DIR, preview)
        print(f"    预览: {preview}")
    print()

def cmd_build(args):
    """仅重新编译签名当前 APK"""
    manifest = load_manifest()
    builder = ApkBuilder()
    builder.write_appfilter(manifest)
    final_apk = builder.build_apk(DEFAULT_APK_OUT)
    print(f"\n✅ 编译签名完成！包含 {len(manifest)} 个图标: {final_apk}\n")
    if getattr(args, "deploy", False):
        device_id = getattr(args, "device", None)
        deployer = IconDeployer(device_id)
        deployer.deploy_all()

def cmd_deploy(args):
    """安装 APK 并自动同步到全局图标包数据库，刷新桌面"""
    device_id = getattr(args, "device", None)
    deployer = IconDeployer(device_id)
    deployer.deploy_all()

# [Main]
def main():
    parser = argparse.ArgumentParser(description="Material You 图标包制作工具")
    subparsers = parser.add_subparsers(dest="command")

    # add 命令
    p_add = subparsers.add_parser("add", help="添加一个应用图标并自动打包")
    p_add.add_argument("image", help="输入的图标图片路径 (PNG/JPG)")
    p_add.add_argument("package_or_name", help="应用包名或应用名称 (如 com.tencent.tmgp.sgame)")
    p_add.add_argument("name", nargs="?", default=None, help="可选：自定义显示名称")
    p_add.add_argument("--deploy", action="store_true", help="构建完成后自动部署到连接的真机")
    p_add.add_argument("--device", default=None, help="目标 ADB 设备序列号 (多设备时指定)")

    # reset 命令
    subparsers.add_parser("reset", help="重置清空所有测试图标")

    # list 命令
    subparsers.add_parser("list", help="列出当前包中的所有应用")

    # build 命令
    p_build = subparsers.add_parser("build", help="重新编译签名 APK")
    p_build.add_argument("--deploy", action="store_true", help="构建完成后自动部署到连接的真机")
    p_build.add_argument("--device", default=None, help="目标 ADB 设备序列号 (多设备时指定)")

    # deploy 命令
    p_deploy = subparsers.add_parser("deploy", help="一键安装并同步到全局图标包生效")
    p_deploy.add_argument("--device", default=None, help="目标 ADB 设备序列号 (多设备时指定)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "reset":
        cmd_reset(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "deploy":
        cmd_deploy(args)

if __name__ == "__main__":
    main()
