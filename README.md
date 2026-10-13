# Thermy9

Installable Windows label studio for the PAPERANG P2S. The native app uses Rust
for rendering and Bluetooth, with the existing web editor inside a Tauri WebView2
window. Python, NumPy and Docker are not required on the destination computer.
Windows security stays enabled.

This repository currently publishes the source. A public Windows binary release
is pending the fresh-PC installation test. Build an installer with the instructions
below; the `dist/` files described here are local build outputs, not tracked files.

This is an independent, unofficial project, not affiliated with or endorsed by
Paperang. Thermy9's original code is **GPL-3.0-only**; see [LICENSE](LICENSE) and
[NOTICE](NOTICE). Third-party licenses remain in force. There is no warranty.

## Start and print

Run **dist/Thermy9_1.0.1_x64-setup.exe**, then open **Thermy9** from Start.
The installer is for Windows 10/11 x64, installs for the current user, and can
download Microsoft's WebView2 runtime if it is missing. Turn on Bluetooth and
the printer, then use **Printer settings → Find printer** on the new computer.
The dedicated app window is titled **Thermy9 · Label Studio**.
Choose Machine, Cable flags, or Image. The preview updates automatically after
edits and includes all requested blank paper. **Print this preview once** sends
the exact preview bytes once, without an automatic retry. Printing is disabled
while a new preview is pending or invalid.

There are only two built-in presets: **Machine label** and **Cable flags**.
Use **Save settings as my preset…** for your own layouts. Settings are stored in
`%APPDATA%/com.thermy9.studio/my-presets.json`; text and image contents are kept separately. Saving an
existing personal name updates that preset. Image mode retains sticker and photo
conversion.

The Save preset dialog includes **Export presets to Downloads** and **Import
presets** for moving layouts between computers. The installer contains neither
your saved presets nor your printer's address. Launching the native executable
from this checkout imports the old `config/` settings once, if no native settings
exist yet. **Start Thermy9 Legacy.cmd** retains the Python/Docker version.
See [installation and build notes](docs/installing.md) for details.
Source releases include the complete corresponding-source archive alongside the
installer. The [release checks](docs/release-checks.md) describe the license review,
privacy checks and fresh-PC test still to be completed.

## Cable labels

Choose **2** or **4** columns total:

- 2: one text field on each side of the fold.
- 4: two fields on each side, e.g. `[name | IP] · fold · [name | IP]`.

Each line in a field is one label row. Use the Copies column for additional copies.
**Repeat both left fields on right** duplicates the values to the other side.
Uncheck it for independent values. Blank lines preserve positions; shorter lists
are padded with blank cells. Up to 50 rows are supported, within the total
one-metre limit. Switching back to two columns hides and ignores the second
fields without deleting their text.

Sliders control text size, side inset, label width, row height, spacing, fold gap,
border thickness and corner radius. Four-column mode adds the gap between fields
and the percentage of each side reserved for field 1. For example, a 44 mm label
with 16 px text, 1 mm inset, 2 mm fold gap, 1 mm field gap and 40% field-1 width
fits GB10-01 alongside 192.0.2.10 on each side. Longer values may need tuning.
Overflow is reported by row and field; text is never silently shrunk or clipped.
Borders can surround each whole row or each half, with an optional dotted fold.

## Paper and text spacing

**Start blank margin** and **End feed / tear-off space** are independent sliders.
Defaults are 0 mm at the start and 14 mm at the end. There is no additional hidden
feed in the print bridge. A zero start adds no blank raster rows, but the app
cannot retract paper already exposed beyond the print head. End feed also affects
the blank paper before the next print. Tune the end feed to your tear edge.
Dimensions are approximate and depend on the current printer calibration.

Use **Text inset from side borders** instead of typing spaces. Machine labels
also offer alignment, font family and label length. Labels use continuous paper;
pre-cut stock gap sensing is not implemented.

## Build the native installer

With Docker Desktop, Node.js/npm and Rust/Cargo available, run `./Build Native.ps1`.
This compiles Windows binaries in Linux, tests the renderer, collects dependency
notices, and packages the NSIS installer in `dist/`. Docker is a build tool only.
On a Windows development machine that permits Rust build helpers and has MSVC
Build Tools, `npm ci` followed by `npm run build:native` also builds directly.

- `native/src/render.rs`: native layout, icons, image conversion and exact previews
- `native/src/printer.rs`: Rust Bluetooth transport and Paperang protocol
- `native/src/main.rs`: desktop commands, preview jobs and per-user presets
- `web/`: shared editor, embedded into the installed app

## Legacy setup and development

Install Python 3.13, Git and Docker Desktop, then run `./setup.ps1` in PowerShell.
Windows needs only Bleak; NumPy and the upstream rendering stack run in Linux.
No Bluetooth passthrough is needed. A local HTTP server binds only to 127.0.0.1; Edge opens it in an app window. Rendering containers run
without network or host mounts, as a non-root user on a read-only filesystem.

- `src/editor.py`: live desktop editor and exact-preview print workflow
- `src/editor_presets.py`: two defaults and personal preset storage
- `src/printer_ble.py`: Bluetooth framing, CRC validation and one-shot sending
- `src/render_bridge.py`: bounded Docker jobs and raster validation
- `docker/render.py`: text, cable and image renderer
- `src/thermy9.py`, `src/label_presets.py`: legacy interface, not used by launcher

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
docker build -t thermy9-render:local -f docker/Dockerfile .
```

The user has confirmed physical prints, including two-column cable labels.
See `docs/validation.md` for the latest software checks and remaining limits.
Upstream references and retained licenses:
https://github.com/wyrtensi/paperang-cli and
https://github.com/createskyblue/paperang-miaomiaoji-tool-gen2 (`src/vendor`).

## Field order and alignment

The web cable editor has an independent **Swap fields** button above each side
in four-column mode. The editor columns move to match the print. Each field has
an **Align left / centre / right** selector. Alignment and allocated width stay
with the field when swapped. **Same text on both sides** repeats values only;
order and alignment remain independent. Personal presets store these settings.

## Copies per row

The cable editor has a numeric **Copies** column before the text fields. Each new
row starts at 1. Enter a different quantity for individual rows, or enter a number
in **Copies for all rows** and click **Set all**. Counts apply to the complete label
(all fields on both sides), with copies grouped by source row. The preview shows
all copies and the total paper length. Up to 50 printed labels per batch and the
existing paper-length limit apply. Quantities belong to the current text batch,
not the saved layout preset. Text fields and the copies column scroll together.


## Rich text, icons and smaller labels

Machine label length now spans **5–500 mm**. Text and icons support 8–240 px;
row height extends to 100 mm, row/fold gaps to 30 mm, inset/field gaps to 20 mm,
border thickness to 16 px, radius to 20 mm, and start/end feed to 100 mm.
Printable width remains capped at 44 mm. Actual content must still fit, and total
print length retains the existing limit.

Select text and use **Bold selection**, **Regular selection**, or **Apply size**.
Use **Line alignment** to position individual lines left, centre or right. The
editor uses visible formatting markers; the live preview shows the styled result.

**Shift+Enter** or **Line inside label** inserts `[br]` inside a cable row, so two
(or more) text lines remain one complete flag and share its copy count. Ordinary
Enter starts the next flag. Machine labels use normal newlines. The line-spacing
slider controls spacing inside the label, separately from gaps between flags.

**+ Icon** opens a searchable collection of 80 original monochrome vector icons
(network, server, computer, power, plug, warning, arrows, etc.). Choose size and
insert at the cursor in any text field. Cut/paste its marker to move it. Default-
sized icons follow the icon-size slider; custom-sized icons use `[icon:name:24]`.
The icon catalogue lives in `web/icons.json` and is packaged with the renderer;
no font download, emoji support or internet connection is needed.

Examples:

```text
[b]GB10-BM-03[/b][br][regular][size:16]Port-3[/size][/regular]
[icon:network:24] GB10-BM-03
[left]Machine name
[right][size:16]192.0.2.10[/size]
```

The native rich-text renderer is `native/src/render.rs`; rebuild the native app
after changing it or the embedded web interface and icon catalogue. The retained
legacy renderer is `docker/inline_text.py`, served through `src/web_app.py`;
`src/editor.py` is the older Tk interface.

## Hardware icon expansion

The icon library now contains 80 original monochrome designs, including model-
labelled RTX 5090/5080/4090/3090 cards, GB10 and DGX Spark, plus GPU/CPU/TPU/NPU,
workstations, mini PCs, switches, routers, access points, firewalls, modems,
patch panels, Ethernet, fiber, SFP, NAS, SSD, NVMe, RAM, motherboard, power,
cooling and peripheral icons. These are simplified identification drawings,
not official logos. Use at least 48 px for icons containing model numbers.
Search accepts multiple words, e.g. RTX 5090. The icon picker displays result counts.
