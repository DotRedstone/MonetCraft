# Android Dual-Stack Icon Injection & Device Guardrails

## 1. Dual Icon-Injection Stack

On rooted PixelOS / AOSP setups running both **Pixel Launcher Enhanced (`PLEnhanced`)** and **Global Icon Pack (`GIP`)**:

1. **Pixel Launcher Enhanced (`com.drdisagree.pixellauncherenhanced`)**:
   * Reads `assets/appfilter.xml` directly from the installed addon APK (`com.materialyou.honorofkings.addon` by default in `pack.json`).
   * Therefore, any package (including dynamically detected random-package apps) MUST exist in the APK's `assets/appfilter.xml`.
2. **Global Icon Pack (`com.richardluo.globalIconPack`)**:
   * Stores icon mappings in `/data/misc/com.richardluo.globalIconPack/iconPack.db`.
   * Binary `entry` BLOB format: `\x00` + big-endian uint16 length (`struct.pack(">H", len(name))`) + UTF-8 drawable name.
   * Each icon requires both exact component mapping `(pkg, act)` and package fallback `(pkg, "")`, injected into both the addon table (`pack/<addon_pkg>`) and each active host theme pack table (`pack/<host_pkg>`).
   * Always `am force-stop com.richardluo.globalIconPack` before pulling and after pushing `iconPack.db` to prevent stale in-memory writes; restore `chmod 666`, `chown nobody:nobody`, and mirror `.bak`.

## 2. Dynamic Random-Package Apps (e.g. SukiSU Ultra)

Apps that randomize their package name on install cannot be tracked statically in `data/manifest.json`.

* Declare them in `pack.json` under `dynamic_apps` using a stable intent signature (e.g., `intent_action: "android.intent.action.VIEW"`, `intent_data: "ksu://webui"`, `drawable: "ic_com_sukisu_ultra"`).
* During `craft.py deploy` (or `add --deploy` / `build --deploy`), `ApkBuilder.build_apk()` merges detected dynamic mappings into `build_tmp/staged_assets/appfilter.xml` for `aapt2 link`.
* The git-tracked `android/assets/appfilter.xml` remains untouched and free of machine-specific random package names.

## 3. Pixel Launcher Cache Reset Sequence

After installing the APK and patching GIP:
```bash
adb shell "su -c 'rm -f /data/data/com.google.android.apps.nexuslauncher/databases/app_icons.db* && killall com.google.android.apps.nexuslauncher'"
```
Pixel Launcher auto-restarts and rebuilds `app_icons.db` within ~2–3 seconds.

## 4. Strict Privacy & Zero-Residue Rules

* **Zero `/sdcard/` writes**: Never run `adb shell screencap /sdcard/...`. Always stream directly to host PC via `adb exec-out screencap -p`.
* **Zero `/data/local/tmp/` leaks**: Any root file transfer (`iconPack.db`, `app_icons.db`) must be cleaned with `rm -f` inside a `finally` block.
* **Non-intrusive verification**: Prefer inspecting Pixel Launcher's `app_icons.db` via `craft.py verify --out ...` rather than switching the user's active foreground app to take screenshots.
