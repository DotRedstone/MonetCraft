#!/usr/bin/env python3
# [Vectorizer]
# 通用图标资源处理引擎：支持 monet (MD3 动态双色)、adaptive (彩色自适应) 与 bitmap (全彩/异形/线条)

import os
import re
import shutil
import subprocess

from core.config import load_pack_config
from core.env import CONVERT, POTRACE, RESVG


# [SVG & Raster Helpers]
def _recolor_white_svg(svg_text, target_hex, bg_circle_hex=None):
    """将纯白多透明层 mono SVG 转换为指定主色 (及可选圆底) 的预览矢量"""
    r = int(target_hex[1:3], 16)
    g = int(target_hex[3:5], 16)
    b = int(target_hex[5:7], 16)

    out = re.sub(
        r"rgba\(\s*255\s*,\s*255\s*,\s*255\s*,",
        f"rgba({r},{g},{b},",
        svg_text,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"rgb\(\s*255\s*,\s*255\s*,\s*255\s*\)",
        target_hex,
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"#(?:FFFFFF|FFF)\b", target_hex, out, flags=re.IGNORECASE)
    out = re.sub(r'(fill|stroke)\s*=\s*"white"', rf'\1="{target_hex}"', out, flags=re.IGNORECASE)

    if bg_circle_hex:
        bg_tag = f'\n  <circle cx="512" cy="512" r="470" fill="{bg_circle_hex}"/>'
        out = re.sub(r"(<svg\b[^>]*>)", r"\1" + bg_tag, out, count=1)
    return out


def _is_hex_color(val):
    return bool(val and re.fullmatch(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", val.strip()))


def _find_asset(assets_dir, stem):
    """在 assets/ 中按 .svg 优先、.png 次之查找源文件"""
    for ext in (".svg", ".png"):
        p = os.path.join(assets_dir, stem + ext)
        if os.path.exists(p):
            return p
    return None


# [Service]
class IconVectorizer:
    def __init__(self, tmp_dir, pack_config=None):
        self.tmp_dir = tmp_dir
        os.makedirs(tmp_dir, exist_ok=True)
        self.cfg = pack_config or load_pack_config()
        self.icon_size = int(self.cfg.get("icon_size", 512))
        self.palette = self.cfg["palette"]
        raw_overrides = self.cfg.get("visual_center_overrides", {})
        self.center_overrides = {k: tuple(v) for k, v in raw_overrides.items()}

    # [Monet Raster Auto-Vectorization]
    def process(self, img_path, base_name, output_dir, assets_dir):
        """
        自动将输入位图矢量化为 Material You (monet) 双色分层矢量与 512px 位图
        """
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(assets_dir, exist_ok=True)

        preprocessed = f"{self.tmp_dir}/{base_name}_prep.png"
        mask_draw = "fill-rule evenodd path 'M 0,0 H 1024 V 1024 H 0 Z M 512,82 A 430,430 0 1,1 511.99,82 Z'"
        subprocess.run([
            CONVERT, img_path,
            "-resize", "1024x1024!",
            "-fill", "white", "-draw", mask_draw,
            preprocessed,
        ], check=True)

        colors = self._get_palette(preprocessed)
        primary_hex = colors.get("primary", "#024855")
        secondary_hex = colors.get("secondary")
        bg_hex = colors.get("bg", "#A7E4FD")

        if not secondary_hex:
            return self._fallback_single_tone(preprocessed, base_name, output_dir, assets_dir, bg_hex, primary_hex)

        p_pbm = f"{self.tmp_dir}/{base_name}_pri"
        p_paths = self._extract_layer(preprocessed, primary_hex, p_pbm)
        s_paths = self._extract_layer(preprocessed, secondary_hex, f"{self.tmp_dir}/{base_name}_sec")

        if not s_paths:
            return self._fallback_single_tone(preprocessed, base_name, output_dir, assets_dir, bg_hex, primary_hex)

        if base_name in self.center_overrides:
            cx, cy = self.center_overrides[base_name]
        else:
            cx, cy = self._get_shape_bounds([f"{p_pbm}.pbm", f"{self.tmp_dir}/{base_name}_sec.pbm"])
        transform_val = f"translate(512, 512) scale(0.65) translate({-cx:.2f}, {-cy:.2f}) translate(0, 1024) scale(0.1, -0.1)"
        pri_d = " ".join(p_paths)
        sec_d = " ".join(s_paths)

        def make_svg(bg, pri, sec):
            circle = f'<circle cx="512" cy="512" r="470" fill="{bg}"/>' if bg else ""
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">\n'
                f"  {circle}\n"
                f'  <g transform="{transform_val}">\n'
                f'    <path fill="{sec}" d="{sec_d}" />\n'
                f'    <path fill="{pri}" d="{pri_d}" />\n'
                "  </g>\n"
                "</svg>"
            )

        pal = self.palette
        svg_sky = make_svg(pal["light_bg"], pal["light_fg"], pal["light_fg_sec"])
        svg_dark = make_svg(pal["dark_bg"], pal["dark_fg"], pal["dark_fg_sec"])
        svg_mono = make_svg(None, "#FFFFFF", "rgba(255,255,255,0.48)")
        svg_fg = make_svg(None, pal["light_fg"], pal["light_fg_sec"])

        paths = self._write_and_render_monet(base_name, assets_dir, output_dir, svg_sky, svg_dark, svg_fg, svg_mono)
        paths["paths_primary"] = pri_d
        paths["paths_secondary"] = sec_d
        return paths

    # [Universal Multi-Style Import]
    def import_svg(self, mono_svg_path, base_name, output_dir, assets_dir):
        """兼容快捷入口：导入 monet 多透明层纯白 SVG"""
        return self.import_icon(mono_svg_path, base_name, output_dir, assets_dir, style="monet")

    def import_icon(self, src_path, base_name, output_dir, assets_dir, style="monet", bg=None, mono_path=None):
        """
        通用图标导入入口，按 style 分派：
        - monet:    导入多透明层纯白 SVG，自动派生 sky/dark/fg 与全套 PNG
        - adaptive: 导入彩色前景 (SVG/PNG) + 背景 (色值或 SVG/PNG) + 可选单色蒙版
        - bitmap:   导入任意全彩/异形/线条图标 (SVG/PNG)，保持原始轮廓与透明通道
        """
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(assets_dir, exist_ok=True)
        ext = os.path.splitext(src_path)[1].lower()

        if style == "monet":
            if ext != ".svg":
                raise RuntimeError("monet 模式导入要求输入 .svg 文件 (位图自动矢量化请使用 craft.py add)")
            with open(src_path, "r", encoding="utf-8") as f:
                svg_mono = f.read()
            pal = self.palette
            svg_fg = _recolor_white_svg(svg_mono, pal["light_fg"])
            svg_sky = _recolor_white_svg(svg_mono, pal["light_fg"], bg_circle_hex=pal["light_bg"])
            svg_dark = _recolor_white_svg(svg_mono, pal["dark_fg"], bg_circle_hex=pal["dark_bg"])
            return self._write_and_render_monet(base_name, assets_dir, output_dir, svg_sky, svg_dark, svg_fg, svg_mono)

        if style == "bitmap":
            if ext not in (".svg", ".png", ".webp", ".jpg", ".jpeg"):
                raise RuntimeError(f"不支持的图标格式: {ext}")
            # 矢量保留 .svg 源文件，位图统一规范化存为透明 .png 源文件
            if ext == ".svg":
                dest_src = os.path.join(assets_dir, f"{base_name}.svg")
                if os.path.abspath(src_path) != os.path.abspath(dest_src):
                    shutil.copyfile(src_path, dest_src)
            else:
                dest_src = os.path.join(assets_dir, f"{base_name}.png")
                self.normalize_raster(src_path, dest_src, self.icon_size)
            normal_png = os.path.join(output_dir, f"{base_name}_normal_512.png")
            self.render_any(dest_src, normal_png, self.icon_size)
            return {"style": "bitmap", "source": dest_src, "normal_png": normal_png}

        if style == "adaptive":
            fg_ext = ".svg" if ext == ".svg" else ".png"
            dest_fg_src = os.path.join(assets_dir, f"{base_name}_fg{fg_ext}")
            if fg_ext == ".svg":
                if os.path.abspath(src_path) != os.path.abspath(dest_fg_src):
                    shutil.copyfile(src_path, dest_fg_src)
            else:
                self.normalize_raster(src_path, dest_fg_src, self.icon_size)

            bg_color = None
            dest_bg_src = None
            if bg:
                if _is_hex_color(bg):
                    bg_color = bg.strip().upper()
                elif os.path.exists(bg):
                    bg_ext = ".svg" if bg.lower().endswith(".svg") else ".png"
                    dest_bg_src = os.path.join(assets_dir, f"{base_name}_bg{bg_ext}")
                    if bg_ext == ".svg":
                        if os.path.abspath(bg) != os.path.abspath(dest_bg_src):
                            shutil.copyfile(bg, dest_bg_src)
                    else:
                        self.normalize_raster(bg, dest_bg_src, self.icon_size)
                else:
                    raise FileNotFoundError(f"背景参数既不是有效十六进制色值也不是存在的文件: {bg}")
            else:
                bg_color = "#FFFFFF"

            if mono_path:
                if not os.path.exists(mono_path):
                    raise FileNotFoundError(f"找不到单色蒙版文件: {mono_path}")
                m_ext = ".svg" if mono_path.lower().endswith(".svg") else ".png"
                dest_mono_src = os.path.join(assets_dir, f"{base_name}_mono{m_ext}")
                if m_ext == ".svg":
                    if os.path.abspath(mono_path) != os.path.abspath(dest_mono_src):
                        shutil.copyfile(mono_path, dest_mono_src)
                else:
                    self.normalize_raster(mono_path, dest_mono_src, self.icon_size)

            return self.render_from_assets(
                base_name, assets_dir, output_dir, style="adaptive", bg_color=bg_color
            )

        raise RuntimeError(f"不支持的图标风格: {style} (可选: monet / adaptive / bitmap)")

    # [Single-Source Sync Renderer]
    def render_from_assets(self, base_name, assets_dir, output_dir, style="monet", bg_color=None):
        """从 assets/ 源文件按 style 重渲染全部输出 PNG"""
        os.makedirs(output_dir, exist_ok=True)
        size = self.icon_size

        if style == "bitmap":
            src = _find_asset(assets_dir, base_name)
            if not src:
                raise FileNotFoundError(f"缺少 bitmap 图标源文件: {assets_dir}/{base_name}.(svg|png)")
            normal_png = os.path.join(output_dir, f"{base_name}_normal_512.png")
            self.render_any(src, normal_png, size)
            return {"style": "bitmap", "normal_png": normal_png}

        if style == "adaptive":
            fg_src = _find_asset(assets_dir, f"{base_name}_fg")
            if not fg_src:
                raise FileNotFoundError(f"缺少 adaptive 前景源文件: {assets_dir}/{base_name}_fg.(svg|png)")
            fg_png = os.path.join(output_dir, f"{base_name}_fg_512.png")
            self.render_any(fg_src, fg_png, size)

            bg_src = _find_asset(assets_dir, f"{base_name}_bg")
            bg_png = None
            if bg_src:
                bg_png = os.path.join(output_dir, f"{base_name}_bg_512.png")
                self.render_any(bg_src, bg_png, size)

            mono_src = _find_asset(assets_dir, f"{base_name}_mono")
            mono_png = None
            if mono_src:
                mono_png = os.path.join(output_dir, f"{base_name}_mono_512.png")
                self.render_any(mono_src, mono_png, size)

            # 合成完整预览图供传统启动器回退使用
            normal_png = os.path.join(output_dir, f"{base_name}_normal_512.png")
            if bg_png:
                subprocess.run([CONVERT, bg_png, fg_png, "-gravity", "center", "-composite", normal_png], check=True)
            else:
                fill = bg_color or "#FFFFFF"
                subprocess.run([
                    CONVERT, "-size", f"{size}x{size}", f"xc:{fill}",
                    fg_png, "-gravity", "center", "-composite", normal_png,
                ], check=True)

            res = {
                "style": "adaptive",
                "normal_png": normal_png,
                "fg_png": fg_png,
                "bg_color": bg_color if not bg_png else None,
            }
            if bg_png:
                res["bg_png"] = bg_png
            if mono_png:
                res["mono_png"] = mono_png
            return res

        # 默认 monet 风格
        sky_path = os.path.join(assets_dir, f"{base_name}_sky.svg")
        dark_path = os.path.join(assets_dir, f"{base_name}_dark.svg")
        fg_path = os.path.join(assets_dir, f"{base_name}_fg.svg")
        mono_path = os.path.join(assets_dir, f"{base_name}_mono.svg")
        if not os.path.exists(mono_path):
            raise FileNotFoundError(f"缺少 monet 矢量源文件: {mono_path}")
        if not (os.path.exists(sky_path) and os.path.exists(dark_path) and os.path.exists(fg_path)):
            return self.import_icon(mono_path, base_name, output_dir, assets_dir, style="monet")

        normal_png = os.path.join(output_dir, f"{base_name}_normal_512.png")
        dark_png = os.path.join(output_dir, f"{base_name}_dark_512.png")
        fg_png = os.path.join(output_dir, f"{base_name}_fg_512.png")
        mono_png = os.path.join(output_dir, f"{base_name}_mono_512.png")

        self.render_svg(sky_path, normal_png, size)
        self.render_svg(dark_path, dark_png, size)
        self.render_svg(fg_path, fg_png, size)
        self.render_svg(mono_path, mono_png, size)
        return {
            "style": "monet",
            "svg_sky": sky_path,
            "svg_dark": dark_path,
            "svg_fg": fg_path,
            "svg_mono": mono_path,
            "normal_png": normal_png,
            "dark_png": dark_png,
            "fg_png": fg_png,
            "mono_png": mono_png,
        }

    def _write_and_render_monet(self, base_name, assets_dir, output_dir, svg_sky, svg_dark, svg_fg, svg_mono):
        sky_path = os.path.join(assets_dir, f"{base_name}_sky.svg")
        dark_path = os.path.join(assets_dir, f"{base_name}_dark.svg")
        fg_path = os.path.join(assets_dir, f"{base_name}_fg.svg")
        mono_path = os.path.join(assets_dir, f"{base_name}_mono.svg")

        for path, content in ((sky_path, svg_sky), (dark_path, svg_dark), (fg_path, svg_fg), (mono_path, svg_mono)):
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

        normal_png = os.path.join(output_dir, f"{base_name}_normal_512.png")
        dark_png = os.path.join(output_dir, f"{base_name}_dark_512.png")
        fg_png = os.path.join(output_dir, f"{base_name}_fg_512.png")
        mono_png = os.path.join(output_dir, f"{base_name}_mono_512.png")

        self.render_svg(sky_path, normal_png, self.icon_size)
        self.render_svg(dark_path, dark_png, self.icon_size)
        self.render_svg(fg_path, fg_png, self.icon_size)
        self.render_svg(mono_path, mono_png, self.icon_size)

        return {
            "style": "monet",
            "svg_sky": sky_path,
            "svg_dark": dark_path,
            "svg_fg": fg_path,
            "svg_mono": mono_path,
            "normal_png": normal_png,
            "dark_png": dark_png,
            "fg_png": fg_png,
            "mono_png": mono_png,
        }

    # [Image Analysis Internals]
    def _get_palette(self, img):
        cmd = [
            CONVERT, img, "-scale", "100x100", "+dither", "-colors", "10",
            "-define", "histogram:unique-colors=true", "-format", "%c", "histogram:info:",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        colors = []
        for line in res.stdout.splitlines():
            m = re.search(r"#([0-9A-Fa-f]{6})", line)
            count_m = re.search(r"^\s*(\d+):", line)
            if m and count_m:
                count = int(count_m.group(1))
                hex_val = "#" + m.group(1).upper()
                r, g, b = int(hex_val[1:3], 16), int(hex_val[3:5], 16), int(hex_val[5:7], 16)
                bri = (r * 299 + g * 587 + b * 114) / 1000
                colors.append((count, hex_val, bri))

        valid = [c for c in colors if 10 < c[2] < 240]
        pri_candidates = sorted([c for c in valid if c[2] < 100], key=lambda x: x[2])
        pri = pri_candidates[0][1] if pri_candidates else "#024855"

        sec_candidates = sorted(
            [c for c in valid if 100 <= c[2] <= 185 and 350 <= c[0] <= 2200],
            key=lambda x: x[0],
            reverse=True,
        )
        sec = sec_candidates[0][1] if sec_candidates else None

        bg_candidates = sorted([c for c in colors if 200 <= c[2] <= 235], key=lambda x: x[0], reverse=True)
        bg = bg_candidates[0][1] if bg_candidates else "#A7E4FD"
        return {"bg": bg, "primary": pri, "secondary": sec}

    def _is_bg_layer(self, pbm_path):
        if not os.path.exists(pbm_path):
            return True
        try:
            with open(pbm_path, "rb") as f:
                line = f.readline()
                while line.startswith(b"#") or line == b"P4\n":
                    line = f.readline()
                _w, _h = map(int, line.split())
                data = f.read()
            if sum(bin(b).count("1") for b in data) > 220000:
                return True
        except Exception:
            pass
        return False

    def _extract_layer(self, img, hex_val, out_prefix, fuzz=18):
        pbm = f"{out_prefix}.pbm"
        svg = f"{out_prefix}.svg"
        subprocess.run([
            CONVERT, img,
            "-fuzz", f"{fuzz}%",
            "-fill", "black", "-opaque", hex_val,
            "-fill", "white", "+opaque", "black",
            pbm,
        ], check=True)
        if self._is_bg_layer(pbm):
            return []
        subprocess.run([POTRACE, pbm, "-s", "-a", "1.1", "-t", "10", "--opttolerance", "0.2", "-o", svg], check=True)
        with open(svg, "r", encoding="utf-8") as f:
            content = f.read()
        paths = re.findall(r'<path[^>]*d="([^"]+)"', content)
        return [p for p in paths if not (p.startswith("M0 ") or " 5120 0 0 5120" in p or "M0 1024" in p)]

    def _get_shape_bounds(self, pbm_paths):
        comb = None
        w, h = 0, 0
        for path in pbm_paths:
            if not os.path.exists(path) or self._is_bg_layer(path):
                continue
            try:
                with open(path, "rb") as fp:
                    line = fp.readline()
                    while line.startswith(b"#") or line == b"P4\n":
                        line = fp.readline()
                    w, h = map(int, line.split())
                    data = bytearray(fp.read())
                if comb is None:
                    comb = data
                else:
                    for i in range(len(comb)):
                        comb[i] |= data[i]
            except Exception:
                continue

        if comb is None:
            return 512.0, 512.0

        row_bytes = (w + 7) // 8
        row_counts = [0] * h
        col_counts = [0] * w
        for y in range(h):
            offset = y * row_bytes
            for byte_idx in range(row_bytes):
                b = comb[offset + byte_idx]
                if b:
                    for bit in range(8):
                        if (b >> (7 - bit)) & 1:
                            x = byte_idx * 8 + bit
                            if x < w:
                                row_counts[y] += 1
                                col_counts[x] += 1

        valid_cols = [x for x in range(w) if col_counts[x] >= 4]
        valid_rows = [y for y in range(h) if row_counts[y] >= 4]
        if not valid_cols or not valid_rows:
            return 512.0, 512.0

        cx = (valid_cols[0] + valid_cols[-1]) / 2.0
        cy = (valid_rows[0] + valid_rows[-1]) / 2.0
        return round(cx, 2), round(cy, 2)

    def _fallback_single_tone(self, img, base_name, output_dir, assets_dir, bg_hex, primary_hex):
        pbm = f"{self.tmp_dir}/{base_name}_single.pbm"
        svg = f"{self.tmp_dir}/{base_name}_single.svg"
        subprocess.run([
            CONVERT, img,
            "-fuzz", "30%",
            "-fill", "black", "-opaque", primary_hex,
            "-fill", "white", "+opaque", "black",
            pbm,
        ], check=True)
        subprocess.run([POTRACE, pbm, "-s", "-a", "1.1", "-t", "8", "--opttolerance", "0.2", "-o", svg], check=True)
        with open(svg, "r", encoding="utf-8") as f:
            raw = f.read()
        paths = re.findall(r'<path[^>]*d="([^"]+)"', raw)
        clean = [p for p in paths if not (p.startswith("M0 ") or " 5120 0 0 5120" in p or "M0 1024" in p)]
        combined_d = " ".join(clean)

        if base_name in self.center_overrides:
            cx, cy = self.center_overrides[base_name]
        else:
            cx, cy = self._get_shape_bounds([pbm])
        transform_val = f"translate(512, 512) scale(0.65) translate({-cx:.2f}, {-cy:.2f}) translate(0, 1024) scale(0.1, -0.1)"

        def make_clip_svg(bg, top_fill, bot_fill):
            circle = f'\n  <circle cx="512" cy="512" r="470" fill="{bg}"/>' if bg else ""
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">\n'
                "  <defs>\n"
                '    <clipPath id="c_top"><rect x="0" y="0" width="1024" height="515"/></clipPath>\n'
                '    <clipPath id="c_bot"><rect x="0" y="515" width="1024" height="509"/></clipPath>\n'
                f'    <g id="icon_shape" transform="{transform_val}"><path d="{combined_d}" /></g>\n'
                "  </defs>"
                f"{circle}\n"
                f'  <g clip-path="url(#c_top)" fill="{top_fill}"><use href="#icon_shape" /></g>\n'
                f'  <g clip-path="url(#c_bot)" fill="{bot_fill}"><use href="#icon_shape" /></g>\n'
                "</svg>"
            )

        pal = self.palette
        svg_sky = make_clip_svg(pal["light_bg"], pal["light_fg_sec"], pal["light_fg"])
        svg_dark = make_clip_svg(pal["dark_bg"], pal["dark_fg_sec"], pal["dark_fg"])
        svg_fg = make_clip_svg(None, pal["light_fg_sec"], pal["light_fg"])
        svg_mono = make_clip_svg(None, "rgba(255,255,255,0.52)", "#FFFFFF")

        res = self._write_and_render_monet(base_name, assets_dir, output_dir, svg_sky, svg_dark, svg_fg, svg_mono)
        res["paths_primary"] = combined_d
        res["paths_secondary"] = combined_d
        return res

    # [Render Primitives]
    @staticmethod
    def render_svg(svg_path, png_path, size=512):
        subprocess.run([RESVG, "-w", str(size), "-h", str(size), svg_path, png_path], check=True)

    @staticmethod
    def normalize_raster(src_path, dst_png, size=512):
        subprocess.run([
            CONVERT, src_path,
            "-background", "none",
            "-resize", f"{size}x{size}",
            "-gravity", "center",
            "-extent", f"{size}x{size}",
            f"PNG32:{dst_png}",
        ], check=True)

    @classmethod
    def render_any(cls, src_path, png_path, size=512):
        if src_path.lower().endswith(".svg"):
            cls.render_svg(src_path, png_path, size)
        else:
            cls.normalize_raster(src_path, png_path, size)
