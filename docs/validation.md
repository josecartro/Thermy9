# Validation — 2026-10-13

## Current editor

- Docker image rebuilt successfully with live-preview rendering and 2/4 columns.
- Two default presets render; user presets round-trip, including four-column settings.
- Leading/trailing blank raster rows and total byte count verified. Default feed
  is 0 mm leading / 14 mm trailing and is included in the exact PNG preview.
- Text padding changes render successfully. Machine default renders successfully.
- Both image conversion modes render successfully with configurable end feed.
- Four-column name/IP preview visually inspected (`four-column-preview.png`).
- Independent unequal four-column lists preserve blank row positions; overflow
  is rejected with row/field information.
- Tk live auto-render, paired-field mirroring, visibility and mode switching pass.
- Unit suite covers personal presets, corrupt-file preservation, stale-preview
  rejection, exact cached-byte sending, paper-use gating, no retries and protocol
  CRC/fragmentation handling.
- No physical print sent during this editor update. Feed/tear alignment and
  four-column readability still need user assessment on paper. Long physical
  batches remain unverified.

## Hardware already verified

The user confirmed earlier physical printing and provided a successful bordered
2-column cable label photo. Printer advertises Paperang_P2 at AA:BB:CC:DD:EE:FF.
Native protocol replies returned firmware 1.0.11, battery 100%, status byte 00.
BLE and classic discovery both found it. The responsive service is 49535343;
FF00/A5 did not respond. No Windows security policy was changed.

## Windows dependency workaround

The original Windows upstream CLI could not import NumPy because Smart App
Control blocked `_umath_linalg.cp313-win_amd64.pyd`. That CLI is no longer used
by Thermy9. Rendering runs in Linux Docker, with native Windows Bleak handling
Bluetooth. There is no need to disable security or approve the blocked DLL.

Linux renderer uses paperang-cli revision
73b8f08c80be3ffc956ce9754cc9d2f171855ff1. Protocol references also include
createskyblue/paperang-miaomiaoji-tool-gen2 revision
ee2fbb059550a2b5891a815ef0db08bb428e07d2. Licenses are retained in src/vendor.

## Flexible fields and preview guides — 2026-10-13

Four-column cable layouts now let fields borrow unused width from their neighbour
(default on), keeping a consistent split across rows on each side. The percentage
slider is a preferred split; disable “Let fields share spare space” for fixed widths.
No text resizing or clipping is introduced. Show rulers and lines adds millimetre
rulers, actual field/row boundaries, fold space and feed boundaries to the preview
only. Guide geometry comes from the renderer and is never sent to the printer.

Verified GB10-BM-03 / Port-3 with the user's screenshot settings: 42 mm width,
16 px regular text, 2.5 mm inset, 4 mm fold space, 1 mm field gap, 40% preferred
field-1 width. Verified aligned rows, non-overlapping fields, fixed-mode rejection,
true overflow rejection and unchanged print bytes with guides. Exact print preview
visually inspected in flexible-fields-preview.png. All 18 unit tests passed;
JavaScript syntax check passed. No physical print sent. Browser overlay visual
verification remains unavailable after the prior Computer Use URL-policy stop.

## Per-side swaps and field alignment — 2026-10-13

Verified all four left/right swap combinations with left, centre and right
alignment using actual renderer text positions. Verified mirrored GB10-BM-03 /
Port-3 can print NAME/PORT on the left and PORT/NAME on the right. Field widths
and preview guide rectangles follow the swapped fields. Two container tests
(including 12 layout combinations) and 18 existing tests passed. JS syntax check
passed. No physical print used. Run container checks with:

```powershell
Get-Content tests/cable_layout_checks.py -Raw | docker run --rm -i --network=none --read-only --entrypoint python thermy9-render:local -
```

## Row copy counts — 2026-10-13

Added per-row numeric copies (default 1), Set all, grouped expansion and source-row
versus printed-label totals. Verified exact repeated raster rows for [4,2] counts
in two- and four-column layouts with independent right values and swapped fields.
Confirmed feed is applied once per batch, spacing between all printed rows, default
counts, and rejection of zero, fractions, strings, booleans and over-limit batches.
Four renderer tests and 18 application tests passed; JS syntax check passed. No
physical paper used. Counts are not part of styling presets.

## Rich text and range expansion — 2026-10-13

Added mixed font sizes, bold/regular spans, per-line alignment, inline vector icons
and multiline cable cells without changing source-row/copy semantics. Twenty
original icons are shared between the picker and renderer. Markers are shown in
the editor, with the formatted result in the exact raster preview. No WYSIWYG
editor claim: free-positioned drag-and-drop objects are not implemented.

Five new renderer checks cover 5 mm machine labels, font runs, icon measurements,
all catalogue icons, two-line flags with copies, line alignment and overflow.
Four cable-layout and 18 application tests also passed. Rich flag and machine PNGs
were visually inspected (rich-flags-preview.png, rich-machine-preview.png). JS
syntax check passed. Browser interactions and physical print quality for the new
features have not been visually/hardware verified. No paper used.

## Hardware icon expansion — 2026-10-13

Catalogue expanded from 20 to 80 original icons. Added labelled icon primitives
and numeric IDs (rtx-5090, gb10). All 80 have rendered ink; six rich-render checks
passed, including model token parsing and explicit icon dimensions. JS syntax
passed. Hardware sample visually checked in hardware-icons-preview.png. No paper
used. Small embedded model labels need adequate icon size; picker suggests 48 px+.

## Native Rust/Tauri installer — 2026-10-13

Built `dist/Thermy9_1.0.0_x64-setup.exe` (4.12 MiB), installed it successfully
for the current Windows user (installer exit 0), and opened the installed app.
Start-menu shortcut and uninstaller were verified. The Rust renderer, fonts,
80 icons and web editor are embedded; the app has no Python/NumPy/Docker runtime
dependency. PE imports contain only Windows system/UCRT DLLs, not a separately
required Visual C++ runtime. WebView2 is handled by the installer.

Native Rust compilation on Windows encountered policy error 4551 for a Cargo
build helper. Building the Windows executable inside Linux with cargo-xwin worked.
Both the finished executable and installer ran under the unchanged Windows
security policy. The installer is unsigned; acceptance on other PCs is unverified.

Verified in the installed WebView2 window: editor loads, default cable preview
renders through native IPC, preset transfer controls display, and Export presets
writes a JSON file matching the original personal presets. Migration from the
checkout's config also matches the original JSON data. Export/import is provided
for moving layouts; duplicate names are rejected without overwriting.

All 12 native tests passed on Windows: 8 renderer tests (5 mm machine labels,
exact PNG/raster agreement, rich multiline flags, 4-column GB10-BM-03/Port-3 fit,
all 80 icons, grouped copies, swaps/alignment, feed margins, image conversion and
invalid inputs) plus protocol CRC/fragmentation/handshake, single-use preview
jobs and preset validation. The 8 renderer tests also passed in Linux. All 18
legacy tests and the JavaScript syntax check passed.

Read-only status checks from both standalone and installed Rust executables
returned "Printer not found". Native Bluetooth status and physical printing
remain unverified on hardware; no paper was used. The retained legacy transport
has previous successful physical prints. Native sends use the same framing and
1008-byte raster blocks, conservative 20-byte BLE writes and no automatic retry.
This may transfer more slowly than the legacy negotiated-MTU sender.

The Start launcher now opens the installed/native app; Start Thermy9 Legacy.cmd
preserves access to the working Python/Docker implementation. Presets are stored
outside the installation under the current user's application data. The installer
does not embed personal settings or the developer's printer address. Font metrics
and dithering can differ from the old renderer; check a physical sample before
printing a large batch with the native version.
