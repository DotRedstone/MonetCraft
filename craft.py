#!/usr/bin/env python3
# [CLI]
# MonetCraft — 通用 Android 图标包补全框架统一命令行入口

import argparse
import os
import sys

from core.auditor import audit_device_coverage, export_device_preview, verify_apk
from core.builder import ApkBuilder
from core.config import (
    ASSETS_DIR,
    BUILD_TMP_DIR,
    OUTPUT_DIR,
    ROOT_DIR,
    VALID_STYLES,
    get_apk_output_path,
    load_manifest,
    load_pack_config,
    save_manifest,
)
from core.deployer import IconDeployer
from core.resolver import AppResolver
from core.vectorizer import IconVectorizer

TMP_VECTOR_DIR = os.path.join(BUILD_TMP_DIR, "vector_work")


# [Helpers]
def _upsert_manifest(manifest, pkg, act, display_name, drawable_name, results, style=None, pack_style="monet"):
    existing = next((it for it in manifest if it["pkg"] == pkg), None)
    aliases = existing.get("aliases") if existing else None
    updated = [it for it in manifest if it["pkg"] != pkg]

    record = {
        "pkg": pkg,
        "activity": act,
        "name": display_name,
        "drawable": drawable_name,
    }
    effective_style = style or results.get("style") or pack_style
    if effective_style != pack_style:
        record["style"] = effective_style
    if results.get("bg_color"):
        record["bg_color"] = results["bg_color"]

    for key in ("normal_png", "dark_png", "fg_png", "bg_png", "mono_png"):
        if results.get(key):
            record[key] = os.path.relpath(results[key], ROOT_DIR)
    if aliases:
        record["aliases"] = aliases

    updated.append(record)
    return updated


def _build_with_optional_dynamic(manifest, device_id=None, include_dynamic=False):
    cfg = load_pack_config()
    apk_out = get_apk_output_path(cfg)
    builder = ApkBuilder(cfg)
    builder.write_appfilter(manifest)
    extra_items = []
    if include_dynamic:
        resolver = AppResolver(device_id)
        extra_items = resolver.detect_dynamic_apps(cfg.get("dynamic_apps", []))
    return builder.build_apk(apk_out, base_items=manifest, extra_items=extra_items)


# [Commands]
def cmd_reset(_args):
    """重置图标包工程，清空历史应用图标"""
    save_manifest([])
    builder = ApkBuilder()
    builder.clean_icons(keep_pack_logo=True)
    apk_path = builder.build_apk(get_apk_output_path())
    print(f"\n✅ 已清空重置图标工程！基础包: {apk_path}\n")


def cmd_add(args):
    """位图自动矢量化入库为 MD3 双色图标并打包"""
    img_path = os.path.abspath(args.image)
    if not os.path.exists(img_path):
        raise FileNotFoundError(f"找不到图片文件: {img_path}")

    cfg = load_pack_config()
    resolver = AppResolver(args.device)
    pkg, act, default_name = resolver.resolve(args.package_or_name)
    display_name = args.name or default_name
    drawable_name = resolver.get_drawable_name(pkg)

    print(f"\n🚀 矢量化位图图标 [monet]: {display_name} ({pkg} / {act} -> {drawable_name})")
    vectorizer = IconVectorizer(TMP_VECTOR_DIR, pack_config=cfg)
    results = vectorizer.process(img_path, drawable_name, OUTPUT_DIR, ASSETS_DIR)

    builder = ApkBuilder(cfg)
    builder.add_icon_resource(
        drawable_name, results["normal_png"], fg_png=results["fg_png"], mono_png=results["mono_png"], style="monet"
    )

    manifest = _upsert_manifest(
        load_manifest(), pkg, act, display_name, drawable_name, results, style="monet", pack_style=cfg["style"]
    )
    save_manifest(manifest)
    final_apk = _build_with_optional_dynamic(manifest, args.device, include_dynamic=args.deploy)

    print(f"🎉 已入库并打包 ({len(manifest)} 个应用): {final_apk}")
    if args.deploy:
        IconDeployer(args.device, pack_config=cfg).deploy_all(final_apk)


def cmd_import(args):
    """导入任意风格的图标源文件 (monet 多层 SVG / adaptive 前景+背景 / bitmap 全彩异形 SVG 或 PNG)"""
    src_path = os.path.abspath(args.source)
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"找不到图标源文件: {src_path}")

    cfg = load_pack_config()
    style = args.style or cfg.get("style", "monet")
    resolver = AppResolver(args.device)
    pkg, act, default_name = resolver.resolve(args.package_or_name)
    display_name = args.name or default_name
    drawable_name = args.drawable or resolver.get_drawable_name(pkg)

    print(f"\n🎨 导入图标 [{style}]: {display_name} ({pkg} / {act} -> {drawable_name})")
    vectorizer = IconVectorizer(TMP_VECTOR_DIR, pack_config=cfg)
    results = vectorizer.import_icon(
        src_path,
        drawable_name,
        OUTPUT_DIR,
        ASSETS_DIR,
        style=style,
        bg=getattr(args, "bg", None),
        mono_path=getattr(args, "mono", None),
    )

    builder = ApkBuilder(cfg)
    builder.add_icon_resource(
        drawable_name,
        results["normal_png"],
        fg_png=results.get("fg_png"),
        mono_png=results.get("mono_png"),
        style=style,
        bg_png=results.get("bg_png"),
        bg_color=results.get("bg_color"),
    )

    manifest = _upsert_manifest(
        load_manifest(), pkg, act, display_name, drawable_name, results, style=style, pack_style=cfg["style"]
    )
    save_manifest(manifest)
    final_apk = _build_with_optional_dynamic(manifest, args.device, include_dynamic=args.deploy)

    print(f"🎉 已导入并打包 ({len(manifest)} 个应用): {final_apk}")
    if args.deploy:
        IconDeployer(args.device, pack_config=cfg).deploy_all(final_apk)


def cmd_sync(_args):
    """从 assets/ 单一数据源并发重渲染并同步全部 Android 资源"""
    cfg = load_pack_config()
    manifest = load_manifest()
    builder = ApkBuilder(cfg)
    count = builder.sync_from_assets(manifest, ASSETS_DIR, OUTPUT_DIR)
    print(f"\n✅ 已从 assets/ 重新渲染并同步 {count} 个图标资源与 appfilter.xml。\n")


def cmd_build(args):
    """编译签名最新 APK (可选 --sync 从 assets/ 干净重渲染 / --deploy 直接推送)"""
    cfg = load_pack_config()
    manifest = load_manifest()
    if args.sync:
        builder = ApkBuilder(cfg)
        count = builder.sync_from_assets(manifest, ASSETS_DIR, OUTPUT_DIR)
        print(f"🔄 已重渲染并同步 {count} 个图标资源。")
    final_apk = _build_with_optional_dynamic(manifest, args.device, include_dynamic=args.deploy)
    print(f"\n✅ 编译签名完成 ({len(manifest)} 个图标, 默认风格: {cfg['style']}): {final_apk}\n")
    if args.deploy:
        IconDeployer(args.device, pack_config=cfg).deploy_all(final_apk)


def cmd_deploy(args):
    """自动合并设备动态包名 (零仓库污染)、安装 APK 并热注入 GIP 刷新桌面"""
    manifest = load_manifest()
    final_apk = _build_with_optional_dynamic(manifest, args.device, include_dynamic=True)
    IconDeployer(args.device).deploy_all(final_apk)


def cmd_audit(args):
    """巡检已连接设备宿主图标包与未适配应用清单"""
    report = audit_device_coverage(args.device)
    hosts = ", ".join(report["host_packs"]) if report["host_packs"] else "未检测到宿主包"
    print(f"\n🔍 设备 {report['device_id']} | 宿主图标包: {hosts}")
    print(f"   桌面图标覆盖率: {report['covered_count']}/{report['total_launchable']}")
    if not report["missing"]:
        print("🎉 所有桌面可启动应用均已覆盖！\n")
        return
    print(f"⚠️ 未适配应用 ({len(report['missing'])} 个):")
    for idx, item in enumerate(report["missing"], 1):
        print(f"  {idx:2d}. {item['label']}  ->  {item['pkg']}/{item['activity']}")
    print()


def cmd_verify(args):
    """校验 APK 资源完整性与 monet 多层 Alpha 质量，可选导出真机缓存实测图"""
    res = verify_apk()
    styles_str = ", ".join(f"{k}:{v}" for k, v in sorted(res["styles"].items()))
    print(f"\n🧪 APK 校验: 共 {res['total']} 个图标 ({styles_str})")
    if res["missing_resources"]:
        print(f"❌ 缺失或异常资源: {', '.join(res['missing_resources'])}")
        sys.exit(1)
    if res["monet"]:
        multi = [r for r in res["monet"] if r["multitone"]]
        single = [r for r in res["monet"] if not r["multitone"]]
        print(f"   Monet Alpha 分层: 多层双色 {len(multi)}/{len(res['monet'])}，纯单色 {len(single)}")
        if single:
            print("   纯单色列表:", ", ".join(r["drawable"] for r in single))
    if args.out:
        cnt, path = export_device_preview(args.out, device_id=args.device)
        print(f"🖼️ 已导出真机缓存实测拼图 ({cnt} 个图标): {path}")
    print()


def cmd_list(_args):
    """列出当前图标包收录的所有应用"""
    cfg = load_pack_config()
    manifest = load_manifest()
    if not manifest:
        print("\n📭 当前图标包为空。\n")
        return
    print(f"\n📋 {cfg['name']} ({cfg['style']}) 当前包含 {len(manifest)} 个应用：")
    for i, it in enumerate(manifest, 1):
        style_tag = f" [{it['style']}]" if it.get("style") and it["style"] != cfg["style"] else ""
        alias_info = f" (+{len(it['aliases'])} aliases)" if it.get("aliases") else ""
        print(f" {i:2d}. [{it['name']}]{style_tag} {it['pkg']}/{it['activity']} -> {it['drawable']}{alias_info}")
    print()


# [Main]
def main():
    parser = argparse.ArgumentParser(description="MonetCraft — 通用 Android 图标包补全框架")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="MD3 位图自动矢量化双色入库并打包")
    p_add.add_argument("image", help="输入图片路径 (PNG/JPG)")
    p_add.add_argument("package_or_name", help="应用包名或名称")
    p_add.add_argument("name", nargs="?", default=None, help="可选：自定义显示名称")
    p_add.add_argument("--deploy", action="store_true", help="构建后立即部署到设备")
    p_add.add_argument("--device", default=None, help="指定 ADB 设备序列号")

    p_imp = sub.add_parser("import", aliases=["import-svg"], help="导入任意风格图标源文件 (monet / adaptive / bitmap)")
    p_imp.add_argument("source", help="输入图标文件路径 (.svg 或 .png)")
    p_imp.add_argument("package_or_name", help="应用包名或名称")
    p_imp.add_argument("name", nargs="?", default=None, help="可选：自定义显示名称")
    p_imp.add_argument("--style", choices=VALID_STYLES, default=None, help="图标风格 (默认取 pack.json style)")
    p_imp.add_argument("--bg", default=None, help="adaptive 风格背景：十六进制色值 (#FFFFFF) 或背景 SVG/PNG 文件")
    p_imp.add_argument("--mono", default=None, help="adaptive 风格可选单色蒙版 SVG/PNG 文件")
    p_imp.add_argument("--drawable", default=None, help="可选：显式指定 drawable 资源名")
    p_imp.add_argument("--deploy", action="store_true", help="构建后立即部署到设备")
    p_imp.add_argument("--device", default=None, help="指定 ADB 设备序列号")

    sub.add_parser("sync", help="从 assets/ 单一数据源并发重渲染并同步全部 Android 资源")

    p_build = sub.add_parser("build", help="编译并签名 APK (不污染 tracked appfilter.xml)")
    p_build.add_argument("--sync", action="store_true", help="编译前先从 assets/ 干净重渲染同步")
    p_build.add_argument("--deploy", action="store_true", help="编译后立即部署到设备")
    p_build.add_argument("--device", default=None, help="指定 ADB 设备序列号")

    p_dep = sub.add_parser("deploy", help="安装 APK 并热注入 GIP，刷新桌面缓存")
    p_dep.add_argument("--device", default=None, help="指定 ADB 设备序列号")

    p_aud = sub.add_parser("audit", help="巡检已连接设备宿主图标包与未适配应用清单")
    p_aud.add_argument("--device", default=None, help="指定 ADB 设备序列号")

    p_ver = sub.add_parser("verify", help="校验 APK 完整性与 Alpha 分层质量，可选导出真机缓存拼图")
    p_ver.add_argument("--out", default=None, help="可选：输出真机 Pixel Launcher 缓存拼图路径")
    p_ver.add_argument("--device", default=None, help="指定 ADB 设备序列号")

    sub.add_parser("list", help="列出当前图标包收录的所有应用")
    sub.add_parser("reset", help="清空重置工程，仅保留基础 pack logo")

    args = parser.parse_args()
    handlers = {
        "add": cmd_add,
        "import": cmd_import,
        "import-svg": cmd_import,
        "sync": cmd_sync,
        "build": cmd_build,
        "deploy": cmd_deploy,
        "audit": cmd_audit,
        "verify": cmd_verify,
        "list": cmd_list,
        "reset": cmd_reset,
    }
    if not args.command:
        parser.print_help()
        sys.exit(0)
    try:
        handlers[args.command](args)
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
