#!/usr/bin/env python3
# [Vectorizer]
# 高精度位图矢量化与 MD3 双色分层引擎

import os
import re
import subprocess

from core.env import CONVERT, POTRACE, RESVG

# [Visual Centering Overrides]
# 当图形包含右下角附加角标/徽章时，机械联合包围盒会导致主体图形偏心失重。
# 此处配置以视觉主元素（如铃铛、盾牌、猫头）对称轴为核心的居中坐标：
VISUAL_CENTER_OVERRIDES = {
    "ic_io_github_magisk317_mipush": (512.0, 518.0),   # 居中对齐 MiPush 铃铛主体
    "ic_com_hidethanox_module": (512.0, 531.0),        # 居中对齐 Hide Thanox 大盾牌
    "ic_com_sukisu_ultra": (512.0, 510.0),             # 居中对齐 SukiSU 猫头主体
}

# [Service]
class IconVectorizer:
    def __init__(self, tmp_dir):
        self.tmp_dir = tmp_dir
        os.makedirs(tmp_dir, exist_ok=True)

    def process(self, img_path, base_name, output_dir, assets_dir):
        """
        自动处理输入图片，生成前景、动态蒙版、SVG 矢量与 512x512 高清图
        返回生成的各个产物路径字典
        """
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(assets_dir, exist_ok=True)

        # 1. 预处理：消除截角黑边与外圈杂色 (r=430 外纯白覆盖)
        preprocessed = f"{self.tmp_dir}/{base_name}_prep.png"
        mask_draw = "fill-rule evenodd path 'M 0,0 H 1024 V 1024 H 0 Z M 512,82 A 430,430 0 1,1 511.99,82 Z'"
        subprocess.run([
            CONVERT, img_path,
            "-resize", "1024x1024!",
            "-fill", "white", "-draw", mask_draw,
            preprocessed
        ], check=True)

        # 2. 颜色聚类与提取
        colors = self._get_palette(preprocessed)
        primary_hex = colors.get("primary", "#024855")
        secondary_hex = colors.get("secondary")
        bg_hex = colors.get("bg", "#A7E4FD")

        # 如果没有识别出次深色，按 Y 轴自然切分产生 MD3 双色纵深
        if not secondary_hex:
            return self._fallback_single_tone(preprocessed, base_name, output_dir, assets_dir, bg_hex, primary_hex)

        # 3. 提取主色层与辅色层矢量
        p_pbm = f"{self.tmp_dir}/{base_name}_pri"
        p_paths = self._extract_layer(preprocessed, primary_hex, p_pbm)
        s_paths = self._extract_layer(preprocessed, secondary_hex, f"{self.tmp_dir}/{base_name}_sec")

        if not s_paths:
            return self._fallback_single_tone(preprocessed, base_name, output_dir, assets_dir, bg_hex, primary_hex)

        # 4. 组装 SVG (施加严格几何居中校准与 0.65 中心安全区缩放)
        if base_name in VISUAL_CENTER_OVERRIDES:
            cx, cy = VISUAL_CENTER_OVERRIDES[base_name]
        else:
            cx, cy = self._get_shape_bounds([f"{p_pbm}.pbm", f"{self.tmp_dir}/{base_name}_sec.pbm"])
        transform_val = f"translate(512, 512) scale(0.65) translate({-cx:.2f}, {-cy:.2f}) translate(0, 1024) scale(0.1, -0.1)"
        pri_d = ' '.join(p_paths)
        sec_d = ' '.join(s_paths)

        def make_svg(bg, pri, sec):
            circle = f'<circle cx="512" cy="512" r="470" fill="{bg}"/>' if bg else ''
            return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  {circle}
  <g transform="{transform_val}">
    <path fill="{sec}" d="{sec_d}" />
    <path fill="{pri}" d="{pri_d}" />
  </g>
</svg>"""

        # 浅色模式: 浅天青容器底 (#BAEAFF) + 深青色主色 (#004D62) + 次深青辅色 (#416D7D) (与 PashaPuma 动态取色 100% 一致)
        svg_sky = make_svg("#BAEAFF", "#004D62", "#416D7D")
        # 深色模式: 暗墨青容器底 (#1D3138) + 浅天青亮线 (#BAEAFF) + 中青灰辅色 (#7595A3)
        svg_dark = make_svg("#1D3138", "#BAEAFF", "#7595A3")
        # 动态蒙版 (透明底，100% 纯白蒙版，供 Android 13+ monochrome 及 tint 动态变色，杜绝半透明背景混色)
        svg_mono = make_svg(None, "#FFFFFF", "#FFFFFF")
        svg_fg = make_svg(None, "#004D62", "#416D7D")

        sky_path = f"{assets_dir}/{base_name}_sky.svg"
        dark_path = f"{assets_dir}/{base_name}_dark.svg"
        fg_path = f"{assets_dir}/{base_name}_fg.svg"
        mono_path = f"{assets_dir}/{base_name}_mono.svg"

        with open(sky_path, "w", encoding="utf-8") as f: f.write(svg_sky)
        with open(dark_path, "w", encoding="utf-8") as f: f.write(svg_dark)
        with open(fg_path, "w", encoding="utf-8") as f: f.write(svg_fg)
        with open(mono_path, "w", encoding="utf-8") as f: f.write(svg_mono)

        # 渲染 512 高清图
        normal_png = f"{output_dir}/{base_name}_normal_512.png"
        dark_png = f"{output_dir}/{base_name}_dark_512.png"
        fg_png = f"{output_dir}/{base_name}_fg_512.png"
        mono_png = f"{output_dir}/{base_name}_mono_512.png"

        self._render(sky_path, normal_png)
        self._render(dark_path, dark_png)
        self._render(fg_path, fg_png)
        self._render(mono_path, mono_png)

        return {
            "svg_sky": sky_path,
            "svg_dark": dark_path,
            "svg_fg": fg_path,
            "svg_mono": mono_path,
            "normal_png": normal_png,
            "dark_png": dark_png,
            "fg_png": fg_png,
            "mono_png": mono_png,
            "paths_primary": pri_d,
            "paths_secondary": sec_d
        }

    def _get_palette(self, img):
        cmd = [CONVERT, img, "-scale", "100x100", "+dither", "-colors", "10", "-define", "histogram:unique-colors=true", "-format", "%c", "histogram:info:"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        colors = []
        for line in res.stdout.splitlines():
            m = re.search(r'#([0-9A-Fa-f]{6})', line)
            count_m = re.search(r'^\s*(\d+):', line)
            if m and count_m:
                count = int(count_m.group(1))
                hex_val = "#" + m.group(1).upper()
                r, g, b = int(hex_val[1:3], 16), int(hex_val[3:5], 16), int(hex_val[5:7], 16)
                bri = (r*299 + g*587 + b*114) / 1000
                colors.append((count, hex_val, bri))

        valid = [c for c in colors if c[2] < 240 and c[2] > 10]

        # 找 primary: 亮度最深 (bri < 100)
        pri_candidates = [c for c in valid if c[2] < 100]
        pri_candidates.sort(key=lambda x: x[2])
        pri = pri_candidates[0][1] if pri_candidates else "#024855"

        # 找 secondary: 亮度在 100 ~ 185 之间，像素数在 350 ~ 2200 之间（排除边缘抗锯齿与背景底板）
        sec_candidates = [c for c in valid if 100 <= c[2] <= 185 and 350 <= c[0] <= 2200]
        sec_candidates.sort(key=lambda x: x[0], reverse=True)
        sec = sec_candidates[0][1] if sec_candidates else None

        # 背景色: 亮度大于 200 中像素数最多者
        bg_candidates = [c for c in colors if 200 <= c[2] <= 235]
        bg_candidates.sort(key=lambda x: x[0], reverse=True)
        bg = bg_candidates[0][1] if bg_candidates else "#A7E4FD"

        return {"bg": bg, "primary": pri, "secondary": sec}

    def _is_bg_layer(self, pbm_path):
        if not os.path.exists(pbm_path):
            return True
        try:
            with open(pbm_path, 'rb') as f:
                line = f.readline()
                while line.startswith(b'#') or line == b'P4\n':
                    line = f.readline()
                w, h = map(int, line.split())
                data = f.read()
            count = sum(bin(b).count('1') for b in data)
            if count > 220000:
                return True
        except Exception:
            pass
        return False

    def _extract_layer(self, img, hex_val, out_prefix, fuzz=18):
        pbm = f"{out_prefix}.pbm"
        svg = f"{out_prefix}.svg"
        cmd_im = [
            CONVERT, img,
            "-fuzz", f"{fuzz}%",
            "-fill", "black", "-opaque", hex_val,
            "-fill", "white", "+opaque", "black",
            pbm
        ]
        subprocess.run(cmd_im, check=True)
        if self._is_bg_layer(pbm):
            return []
        subprocess.run([POTRACE, pbm, "-s", "-a", "1.1", "-t", "10", "--opttolerance", "0.2", "-o", svg], check=True)
        with open(svg, "r", encoding="utf-8") as f:
            content = f.read()
        paths = re.findall(r'<path[^>]*d="([^"]+)"', content)
        return [p for p in paths if not (p.startswith("M0 ") or " 5120 0 0 5120" in p or "M0 1024" in p)]

    def _get_shape_bounds(self, pbm_paths):
        """
        基于全部有效前景图层计算绝对几何包围盒中心，过滤噪点杂边，保证严格居中
        """
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

        # 4px 阈值过滤孤立毛刺和抗锯齿边缘噪点
        valid_cols = [x for x in range(w) if col_counts[x] >= 4]
        valid_rows = [y for y in range(h) if row_counts[y] >= 4]

        if not valid_cols or not valid_rows:
            return 512.0, 512.0

        min_x, max_x = valid_cols[0], valid_cols[-1]
        min_y, max_y = valid_rows[0], valid_rows[-1]

        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        return round(cx, 2), round(cy, 2)

    def _fallback_single_tone(self, img, base_name, output_dir, assets_dir, bg_hex, primary_hex):
        pbm = f"{self.tmp_dir}/{base_name}_single.pbm"
        svg = f"{self.tmp_dir}/{base_name}_single.svg"
        cmd_im = [
            CONVERT, img,
            "-fuzz", "30%",
            "-fill", "black", "-opaque", primary_hex,
            "-fill", "white", "+opaque", "black",
            pbm
        ]
        subprocess.run(cmd_im, check=True)
        subprocess.run([POTRACE, pbm, "-s", "-a", "1.1", "-t", "8", "--opttolerance", "0.2", "-o", svg], check=True)
        with open(svg, "r", encoding="utf-8") as f:
            raw = f.read()
        paths = re.findall(r'<path[^>]*d="([^"]+)"', raw)
        clean = [p for p in paths if not (p.startswith("M0 ") or " 5120 0 0 5120" in p or "M0 1024" in p)]
        combined_d = ' '.join(clean)

        if base_name in VISUAL_CENTER_OVERRIDES:
            cx, cy = VISUAL_CENTER_OVERRIDES[base_name]
        else:
            cx, cy = self._get_shape_bounds([pbm])
        transform_val = f"translate(512, 512) scale(0.65) translate({-cx:.2f}, {-cy:.2f}) translate(0, 1024) scale(0.1, -0.1)"

        svg_sky = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <clipPath id="c_top"><rect x="0" y="0" width="1024" height="515"/></clipPath>
    <clipPath id="c_bot"><rect x="0" y="515" width="1024" height="509"/></clipPath>
    <g id="icon_shape" transform="{transform_val}">
      <path d="{combined_d}" />
    </g>
  </defs>
  <circle cx="512" cy="512" r="470" fill="#BAEAFF"/>
  <g clip-path="url(#c_top)" fill="#416D7D"><use href="#icon_shape" /></g>
  <g clip-path="url(#c_bot)" fill="#004D62"><use href="#icon_shape" /></g>
</svg>"""

        svg_dark = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <clipPath id="c_top"><rect x="0" y="0" width="1024" height="515"/></clipPath>
    <clipPath id="c_bot"><rect x="0" y="515" width="1024" height="509"/></clipPath>
    <g id="icon_shape" transform="{transform_val}">
      <path d="{combined_d}" />
    </g>
  </defs>
  <circle cx="512" cy="512" r="470" fill="#1D3138"/>
  <g clip-path="url(#c_top)" fill="#7595A3"><use href="#icon_shape" /></g>
  <g clip-path="url(#c_bot)" fill="#BAEAFF"><use href="#icon_shape" /></g>
</svg>"""

        svg_fg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <clipPath id="c_top"><rect x="0" y="0" width="1024" height="515"/></clipPath>
    <clipPath id="c_bot"><rect x="0" y="515" width="1024" height="509"/></clipPath>
    <g id="icon_shape" transform="{transform_val}">
      <path d="{combined_d}" />
    </g>
  </defs>
  <g clip-path="url(#c_top)" fill="#416D7D"><use href="#icon_shape" /></g>
  <g clip-path="url(#c_bot)" fill="#004D62"><use href="#icon_shape" /></g>
</svg>"""

        svg_mono = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <g transform="{transform_val}">
    <path fill="#FFFFFF" d="{combined_d}" />
  </g>
</svg>"""

        sky_path = f"{assets_dir}/{base_name}_sky.svg"
        dark_path = f"{assets_dir}/{base_name}_dark.svg"
        fg_path = f"{assets_dir}/{base_name}_fg.svg"
        mono_path = f"{assets_dir}/{base_name}_mono.svg"
        with open(sky_path, "w", encoding="utf-8") as f: f.write(svg_sky)
        with open(dark_path, "w", encoding="utf-8") as f: f.write(svg_dark)
        with open(fg_path, "w", encoding="utf-8") as f: f.write(svg_fg)
        with open(mono_path, "w", encoding="utf-8") as f: f.write(svg_mono)

        normal_png = f"{output_dir}/{base_name}_normal_512.png"
        dark_png = f"{output_dir}/{base_name}_dark_512.png"
        fg_png = f"{output_dir}/{base_name}_fg_512.png"
        mono_png = f"{output_dir}/{base_name}_mono_512.png"

        self._render(sky_path, normal_png)
        self._render(dark_path, dark_png)
        self._render(fg_path, fg_png)
        self._render(mono_path, mono_png)
        return {
            "svg_sky": sky_path,
            "svg_dark": dark_path,
            "svg_fg": fg_path,
            "svg_mono": mono_path,
            "normal_png": normal_png,
            "dark_png": dark_png,
            "fg_png": fg_png,
            "mono_png": mono_png,
            "paths_primary": combined_d,
            "paths_secondary": combined_d
        }

    def _render(self, svg, png):
        subprocess.run([RESVG, "-w", "512", "-h", "512", svg, png], check=True)
