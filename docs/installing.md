# Installing Thermy9

Copy `dist/Thermy9_1.0.1_x64-setup.exe` to a Windows 10/11 x64 computer and run it.
It installs for the signed-in user without requesting administrator privileges.
Open Thermy9 from Start. Bluetooth hardware is required for printing. If WebView2
is absent, installation needs internet access to download Microsoft's runtime.
Once installed, editing, previewing and printing work offline.

There is no Python environment, Docker engine, Rust compiler, NumPy DLL, separate
web server, printer driver or project checkout to install on the target computer.
Fonts, the editor and all 80 icons are included in the executable. Dependency
licenses are installed in `THIRD-PARTY-NOTICES.txt`.
Thermy9 is GPL-3.0-only, without warranty. `LICENSE.txt` and `SOURCE-CODE.txt`
are also installed. When redistributing the installer, provide its matching
`Thermy9-1.0.1-source.zip` alongside it (or equivalent GPL-compliant source access).

## Printer and presets

Turn on the printer and Bluetooth, open Printer settings, choose Find printer,
select the Paperang and Check status. Close other apps connected to that printer.
The implemented protocol is the one previously validated with this PAPERANG P2S;
other printers/models are not automatically compatible.

Use Save preset → Export presets to Downloads on the old computer. Transfer that
JSON file and select it under Import presets on the new one. Import merges new
names and refuses collisions, so existing layouts cannot be silently replaced.
The printer address is configured independently on each computer.

Settings live in `%APPDATA%\com.thermy9.studio`. Back up `my-presets.json` to keep
personal layouts; `printer.json` stores the Bluetooth address. Current text and
image selections are session content and are not included in layout presets.
The installer does not contain the developer's address, presets or label text.

## Windows security

This build is unsigned. The native executable ran on the development PC with its
Windows security policy unchanged. Acceptance on a different PC depends on its
policy; this is not a guarantee that every Smart App Control or managed policy
will allow it. If it is blocked, keep security enabled and use your normal software
approval process. Broad distribution should use an appropriately trusted signing
certificate; none is configured or fabricated here.

The old NumPy dependency has been removed from the native app. During development,
Windows also blocked a Rust build helper; the build script therefore compiles in
a Linux container. The installed app does not run that helper or need Docker.

## Rebuilding

`Build Native.ps1` requires Docker Desktop in Linux-container mode, Node.js/npm
and Rust/Cargo (the Windows packaging CLI uses Cargo metadata). Run it from
PowerShell. It uses the locked Rust/npm dependencies, tests the renderer, generates
license notices, cross-compiles with cargo-xwin and packages a per-user NSIS
installer. Output is in `dist/`. First build downloads the Linux toolchain, crates
and Microsoft CRT/SDK. Subsequent builds reuse Docker volumes.
Use `./Build Native.ps1 -CachePrefix thermy9-clean-check` to compile with a fresh
target cache. This verifies buildability; byte-for-byte reproducibility is not
promised. The corresponding-source archive includes vendored Rust dependencies
and `.cargo/config.toml`, so Cargo can also use those sources without crates.io.
Build tools and Microsoft SDK downloads still require network access initially.

`npm run build:native` is the direct Windows alternative, requiring the MSVC C++
Build Tools and a policy that allows Cargo's build helpers. Regenerate notices
when dependencies change. Versions are in `native/Cargo.toml`,
`native/tauri.conf.json` and their lockfiles.

`dist/thermy9.exe --render-check input.json output-prefix` validates rendering
without opening a window or printing. `--status-check ADDRESS output.json` only
queries the printer. The renderer's PNG and packed print raster describe exactly
the same monochrome pixels. Font layout and image dithering may differ slightly
from the retained Python version; review a preview and one physical sample before
a large batch.

Uninstall through Windows Installed apps. Keep a preset export before uninstalling
or moving computers. The original app remains available through
`Start Thermy9 Legacy.cmd` with its original Python/Docker setup.
