# Style Guide: General Icon Packs (`adaptive` & `bitmap`)

MonetCraft is not limited to Material You. Use this guide when complementing **any** non-MD3 Android icon pack.

## 1. Choosing Between `adaptive` and `bitmap`

| Pack Style Examples | Choose `style` | Why |
| :--- | :--- | :--- |
| **Shapeless / Custom Silhouette / Line / Monochrome White** (`Delta`, `LineX`, `Whicons`, `Crayon`, `Minma`, `CandyCons`, `Viral`) | `bitmap` | Installs raw `res/drawable/<name>.png` with **no** `drawable-anydpi-v26/v33` adaptive XML, preserving exact silhouettes, strokes, drop shadows, and transparency without launcher squircle clipping. |
| **Uniform Adaptive Containers** (`Pixel Icons`, `One UI`, `HyperOS`, `Nothing`, `Flat Squircle`) | `adaptive` | Generates a native `<adaptive-icon>` with separate `<background>` (solid `#RRGGBB` or image) and untinted full-color `<foreground>` (plus optional `<monochrome>`), adapting automatically to any launcher mask shape (circle, squircle, teardrop) and parallax animation. |

You can set `"style"` globally in `pack.json` for a dedicated addon pack, or override `"style"` per app via `craft.py import --style <mode>`.

## 2. Matching Host Pack Visual DNA (Before Drawing)

Before crafting icons for an unfamiliar host pack:
1. Run `craft.py audit` to identify the active host pack package name.
2. Export a small grid of already-themed host icons from the device's `app_icons.db` (or inspect sample icons provided by the user) and extract five concrete design tokens:
   * **Shape & Padding**: full-bleed adaptive (66% safe zone) vs shapeless silhouette (75–85% canvas occupancy) vs uniform squircle corner radius.
   * **Color Palette**: pastel/desaturated (e.g. Delta), neon gradient on dark/transparent (e.g. LineX), pure white glyph (e.g. Whicons), flat Material vibrant, or soft 3D.
   * **Stroke & Detail Budget**: uniform stroke weight (e.g. `28–36px` on `1024` canvas for line packs), rounded vs sharp line caps/joins.
   * **Lighting / Depth**: flat 2D, subtle long shadow, inner highlight, or hand-drawn rough edge.
   * **Optical Balance**: keep visual weight centered on `(512, 512)` with consistent perceived size across round, square, and tall glyphs.

## 3. Importing Assets Cleanly

### `bitmap` Pack Example (Delta / LineX / Whicons / Crayon)
```bash
# Accepts either crisp .svg (recommended, kept in assets/<name>.svg) or transparent .png
python3 craft.py import /path/to/icon.svg com.example.app "Example" --style bitmap --deploy
```

### `adaptive` Pack Example (Pixel / One UI / HyperOS)
```bash
# Solid hex background + full-color foreground SVG/PNG (optional --mono for Android 13+ themed icon fallback)
python3 craft.py import /path/to/fg.svg com.example.app "Example" \
  --style adaptive --bg "#1E88E5" --mono /path/to/mono.svg --deploy

# Or image/gradient SVG background
python3 craft.py import /path/to/fg.svg com.example.app "Example" \
  --style adaptive --bg /path/to/bg.svg --deploy
```

## 4. Visual QA Checklist
* Verify edges are crisp with zero halo/matte artifacts on both dark (`#121212`) and light (`#F5F5F5`) backgrounds.
* For `adaptive`, confirm the foreground stays inside the central **66% safe zone** so circular/squircle launcher masks never clip artwork.
* Run `python3 craft.py verify` to confirm APK resource completeness (`bitmap` must NOT emit adaptive XML; `adaptive` must emit both foreground drawable and v26/v33 XML).
