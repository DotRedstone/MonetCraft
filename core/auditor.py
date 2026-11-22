#!/usr/bin/env python3
# [Auditor]
# 真机未适配图标与宿主主题包巡检、APK 完整性/多层 Alpha 校验及实机缓存拼图导出

from collections import Counter
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile

from core.adb import AdbClient
from core.config import get_apk_output_path, load_manifest, load_pack_config
from core.env import CONVERT


# [APK Verification]
def verify_apk(apk_path=None):
    """
    校验已打包 APK：
    1. 校验 manifest 中全部图标均存在对应 res/drawable/<name>.png 与正确风格 XML
    2. 对 monet 风格图标基于 Alpha 通道直方图峰值识别多层双色 vs 纯单色
    """
    cfg = load_pack_config()
    default_style = cfg.get("style", "monet")
    manifest = load_manifest()
    target = apk_path or get_apk_output_path(cfg)
    if not os.path.exists(target):
        raise FileNotFoundError(f"未找到 APK: {target}")

    missing_res = []
    style_counts = Counter()
    monet_results = []

    with zipfile.ZipFile(target, "r") as zf:
        names = set(zf.namelist())
        seen = set()
        for it in manifest:
            drw = it["drawable"]
            if drw in seen:
                continue
            seen.add(drw)
            style = it.get("style", default_style)
            style_counts[style] += 1

            base_png = f"res/drawable/{drw}.png"
            if base_png not in names:
                missing_res.append(base_png)

            if style == "bitmap":
                if f"res/drawable-anydpi-v26/{drw}.xml" in names:
                    missing_res.append(f"unexpected_adaptive_xml:{drw}")
                continue

            if f"res/drawable-anydpi-v26/{drw}.xml" not in names:
                missing_res.append(f"res/drawable-anydpi-v26/{drw}.xml")

            if style == "monet":
                mono_entry = f"res/drawable/{drw}_mono.png"
                if mono_entry not in names:
                    missing_res.append(mono_entry)
                    continue
                raw = subprocess.check_output(
                    [CONVERT, "png:-", "-alpha", "extract", "-depth", "8", "GRAY:-"],
                    input=zf.read(mono_entry),
                )
                mid_hist = Counter(b for b in raw if 50 <= b <= 215)
                peak_alpha, peak_px = mid_hist.most_common(1)[0] if mid_hist else (0, 0)
                hi_cnt = sum(1 for b in raw if b > 240)
                monet_results.append({
                    "drawable": drw,
                    "peak_alpha": peak_alpha,
                    "peak_px": peak_px,
                    "hi_px": hi_cnt,
                    "multitone": peak_px >= 800,
                })

    return {
        "total": sum(style_counts.values()),
        "styles": dict(style_counts),
        "missing_resources": missing_res,
        "monet": monet_results,
    }


# [Device Audit]
def audit_device_coverage(device_id=None):
    """
    巡检真机：探测 GIP 当前活跃宿主图标包，对比全部可启动应用列出未适配清单
    """
    cfg = load_pack_config()
    adb = AdbClient(device_id, gip_package=cfg["host_gip_package"])
    adb.ensure_connected()

    out = adb.shell(
        "cmd", "package", "query-activities", "--brief",
        "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
        timeout=8,
    )
    launchable = []
    seen_pkgs = set()
    for line in out.splitlines():
        line = line.strip()
        if "/" not in line or line.startswith("Activity") or line.startswith("priority"):
            continue
        pkg, act = line.split("/", 1)
        if act.startswith("."):
            act = pkg + act
        if pkg not in seen_pkgs:
            seen_pkgs.add(pkg)
            launchable.append((pkg, act))

    gip_local = adb.pull_root_file(cfg["gip_db_path"])
    launcher_db_remote = f"/data/data/{cfg['launcher_package']}/databases/app_icons.db"
    launcher_local = None
    covered_pkgs = set()
    host_packs = []
    labels = {}
    try:
        conn = sqlite3.connect(gip_local)
        host_packs = [
            r[0]
            for r in conn.execute("SELECT pack FROM iconPack WHERE pack != ?", (cfg["package_name"],)).fetchall()
        ]
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pack/%'")]
        for tbl in tables:
            for (p,) in conn.execute(f'SELECT DISTINCT packageName FROM "{tbl}"'):
                covered_pkgs.add(p)
        conn.close()

        try:
            launcher_local = adb.pull_root_file(launcher_db_remote)
            lconn = sqlite3.connect(launcher_local)
            for comp, label in lconn.execute("SELECT componentName, label FROM icons"):
                pkg = comp.split("/")[0]
                if pkg not in labels and label:
                    labels[pkg] = label
            lconn.close()
        except Exception:
            pass
    finally:
        if os.path.exists(gip_local):
            os.remove(gip_local)
        if launcher_local and os.path.exists(launcher_local):
            os.remove(launcher_local)

    missing = [
        {"pkg": pkg, "activity": act, "label": labels.get(pkg, pkg)}
        for pkg, act in sorted(launchable)
        if pkg not in covered_pkgs
    ]

    return {
        "device_id": adb.device_id,
        "host_packs": host_packs,
        "total_launchable": len(launchable),
        "covered_count": len(launchable) - len(missing),
        "missing": missing,
    }


# [Device Cache Preview]
def export_device_preview(out_path, pkgs=None, device_id=None):
    """从真机 Pixel Launcher app_icons.db 导出实机渲染图标拼图 (零设备残留)"""
    cfg = load_pack_config()
    adb = AdbClient(device_id, gip_package=cfg["host_gip_package"])
    adb.ensure_connected()

    if pkgs is None:
        manifest = load_manifest()
        target_pairs = [(it["pkg"], it.get("name", it["pkg"])) for it in manifest]
    else:
        target_pairs = [(p, p) for p in pkgs]

    launcher_db_remote = f"/data/data/{cfg['launcher_package']}/databases/app_icons.db"
    local_db = adb.pull_root_file(launcher_db_remote)
    td = tempfile.mkdtemp(prefix="mc_preview_")
    try:
        conn = sqlite3.connect(local_db)
        rows = conn.execute("SELECT componentName, icon, label FROM icons").fetchall()
        conn.close()

        by_pkg = {}
        for comp, blob, label in rows:
            pkg = comp.split("/")[0]
            if pkg not in by_pkg and blob:
                by_pkg[pkg] = (blob, label or pkg)

        tiles = []
        for idx, (pkg, name) in enumerate(target_pairs):
            if pkg not in by_pkg:
                continue
            blob, label = by_pkg[pkg]
            tile_path = os.path.join(td, f"{idx:03d}.png")
            with open(tile_path, "wb") as f:
                f.write(blob)
            tiles.append((tile_path, name or label))

        if not tiles:
            raise RuntimeError("在设备 Pixel Launcher 缓存中未找到匹配的目标图标")

        cols = 6
        rows_cnt = (len(tiles) + cols - 1) // cols
        width = 40 + cols * 190
        height = 40 + rows_cnt * 220
        cmd = [CONVERT, "-size", f"{width}x{height}", "xc:#1A1C19"]
        for i, (tile_path, disp) in enumerate(tiles):
            r, c = divmod(i, cols)
            x = 30 + c * 190
            y = 25 + r * 220
            cmd += ["(", tile_path, "-resize", "144x144", ")", "-geometry", f"+{x}+{y}", "-composite"]
            cmd += ["-fill", "#E0E3DD", "-pointsize", "16", "-gravity", "NorthWest", "-annotate", f"+{x}+{y+154}", disp[:16]]
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        cmd.append(out_path)
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        return len(tiles), out_path
    finally:
        if os.path.exists(local_db):
            os.remove(local_db)
        shutil.rmtree(td, ignore_errors=True)
