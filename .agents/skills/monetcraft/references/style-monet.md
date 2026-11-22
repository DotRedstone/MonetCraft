# Style Guide: `monet` (Material You / MD3 Dynamic Multi-Tone)

Use this spec when targeting Material You / MD3 dynamic packs such as PashaPuma `Pix Material You` or `Lawnicons`.

## 1. Dynamic Multi-Tone Alpha Layering

Android `adaptive-icon` XML tints a single transparent foreground PNG (`ic_xxx_mono.png`) with `android:tint="@color/fg_themed_icons"` (default `SRC_IN` mode). Because `SRC_IN` preserves source alpha, **multi-tone depth lives purely in the alpha channel of `*_mono.svg`**:

| Layer Role | Recommended Fill in `*_mono.svg` | Typical Usage |
| :--- | :--- | :--- |
| **Primary** | `#FFFFFF` (`alpha = 1.0`) | Front planes, main strokes, focal typography, primary figure |
| **Secondary** | `rgba(255,255,255,0.45)` – `0.65` | Back overlapping windows/links, outer rings, secondary 3D faces, ribbons |
| **Soft Container / Fill** | `rgba(255,255,255,0.34)` – `0.42` | Scalloped M3 badges, speech bubbles, translucent dome/play fills |

* **Never flatten `*_mono.svg` to pure `#FFFFFF`** when the glyph has separable planes.
* Contrast must hold cleanly under both light Monet (`system_accent1_100` bg / `system_accent1_700` fg) and dark Monet (`system_accent2_800` bg / `system_accent1_200` fg).

## 2. Strict Geometric Centering & Safe Zone

* Canvas: `1024 x 1024`, visual footprint inside the **65% safe zone** (~`665px` span, centered at `(512, 512)`).
* **Mandatory transform order**: align union bounding-box center `(cx, cy)` to the origin *before* scaling:
  ```text
  translate(512, 512) scale(0.65) translate(-cx, -cy) translate(0, 1024) scale(0.1, -0.1)
  ```
* **Forbidden**:
  * Scaling directly around `(512, 512)` (amplifies offset drift by `(1 - 0.65) * (cx - 512)`).
  * Pixel centroid centering (`sum(y)/N`), which shifts wide-bottom shapes upward. Always use union bounding-box center with >=4px density noise filtering.
* **Composite icons with corner badges**: anchor on the symmetric main body via `visual_center_overrides` in `pack.json`.

## 3. Simplification & Raster-Split Pitfalls

* Drop native colored background circles/plates (`> 220,000 px`, >20% of canvas).
* Remove unreadable micro-badges and promo text (`"AI+"`, `"第二课堂"`, tiny labels).
* ImageMagick/Potrace layer splitting:
  1. Always pass `-define connected-components:mean-color=true` with `-connected-components` before thresholding.
  2. Never use `-connected-components:keep=ID` to split an outer ring from an overlapping inner glyph—use clean bitwise radial/geometric masks on PBM bytes.
  3. Extract enclosed cavities via direct PBM bitwise `filled[i] & (~orig[i] & 0xFF)`.
