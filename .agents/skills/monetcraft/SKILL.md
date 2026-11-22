---
name: monetcraft
description: >-
  Use this skill when auditing an Android phone for unthemed app icons, matching
  any host icon pack style (Material You / MD3 Monet, adaptive colored packs like
  Pixel/One UI/HyperOS, or shapeless/line/flat packs like Delta/LineX/Whicons/Crayon),
  designing or importing icons, building/verifying the addon APK, or deploying via
  Global Icon Pack and Pixel Launcher Enhanced.
---

# MonetCraft Universal Icon Pack Workflow

This skill guides an AI agent through auditing unthemed apps, matching **whatever host icon pack** the user runs, authoring or importing matching icons, verifying quality, and building/deploying via `craft.py`.

## Environment & Config

* If the host shell injects an incompatible `PYTHONHOME`/`PYTHONPATH` (e.g. Nix sandbox), run commands with `env -u PYTHONHOME -u PYTHONPATH python3 craft.py ...`.
* Pack metadata, default `style` (`monet` | `adaptive` | `bitmap`), `palette`, signing, and `dynamic_apps` live in [`pack.json`](../../../pack.json).
* Per-app mappings, per-icon `style` overrides, and component `aliases` live in [`data/manifest.json`](../../../data/manifest.json).

## End-to-End Workflow

### 1. Audit Device & Identify Host Icon Pack
```bash
python3 craft.py audit
```
This prints:
* Active **host icon pack(s)** registered in Global Icon Pack (e.g. `com.pashapuma.pix.material.you.dark`, `website.leifs.delta`, `com.jndapp.line.x.iconpack`, etc.).
* Coverage count and every unthemed launchable app (`label -> pkg/activity`).

### 2. Match Style & Author Icons
Choose the matching framework `style` based on the user's host icon pack (or the user's explicit preference):

| Host Icon Pack Type | `style` | Reference Guide | Import Command |
| :--- | :--- | :--- | :--- |
| **Material You / MD3** (Pix Material You, Lawnicons) | `monet` | [Monet Spec](./references/style-monet.md) | `craft.py import <mono.svg> <pkg> "[Name]"` (or `craft.py add <raster>`) |
| **Colored Adaptive** (Pixel, One UI, HyperOS, Nothing) | `adaptive` | [General Style Guide](./references/style-general.md) | `craft.py import <fg.svg\|png> <pkg> "[Name]" --style adaptive --bg "#HEX\|bg.svg"` |
| **Shapeless / Line / Flat / Pastel** (Delta, LineX, Whicons, Crayon) | `bitmap` | [General Style Guide](./references/style-general.md) | `craft.py import <icon.svg\|png> <pkg> "[Name]" --style bitmap` |

* **Always read the matching reference guide first** before designing icons.
* For unfamiliar host packs, pull 4–6 rendered host icons from the device cache (never writing to `/sdcard/`) and visually study their exact silhouette, padding, corner radius, stroke thickness, and color palette before drawing new icons.

### 3. Build & Verify Before Deploying
```bash
# Re-render everything cleanly from assets/ single source of truth & sign APK
python3 craft.py build --sync

# Verify resource completeness (and Monet multi-alpha layers when applicable)
python3 craft.py verify
```
* Visually inspect rendered previews (for `monet`, simulate a real Monet palette such as `#B3F1BE` bg + `#15512C` alpha-preserving tint; for `adaptive`/`bitmap`, inspect on both light and dark checker/backdrop) before pushing to the phone.

### 4. Deploy & Verify on Device
```bash
python3 craft.py deploy
```
* `deploy` stages dynamic random-package apps (e.g. SukiSU) inside `build_tmp/staged_assets/` so tracked `android/assets/appfilter.xml` stays clean, installs the APK, updates GIP SQLite DB, and resets Pixel Launcher cache.
* Wait ~2.5s and verify real on-device cached icons without interrupting the user's foreground app:
  ```bash
  python3 craft.py verify --out /tmp/device_verify.png
  ```
* Read [Android Stack Reference](./references/android-stack.md) for PLEnhanced + GIP dual-stack details and strict zero-residue rules.
