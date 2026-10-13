# Setup and building

## Install

Run `Thermy9_1.0.1_x64-setup.exe`, then open **Thermy9** from Start.
The installer is currently a local build output, not a public download.

Requires Windows 10/11 x64 and Bluetooth. Installation may need internet to
install Microsoft WebView2; afterward the app works offline. No Python, Docker
or Rust installation is needed to use the app.

Turn on the printer, then choose **Printer settings → Find printer**.
Close other apps connected to it. The supported model is PAPERANG P2S.

The installer is unsigned. If Windows blocks it, keep security enabled and use
your normal software approval process.

## Move your presets

Use **Save preset → Export presets to Downloads**, then **Import presets** on
the other PC. Presets save layouts, not label text or images. Set up the printer
separately on each PC.

Settings are stored in `%APPDATA%\com.thermy9.studio`.

## Build from source

Install Docker Desktop (Linux containers), Node.js/npm and Rust/Cargo. From the
project folder in PowerShell:

```powershell
.\Build Native.ps1
```

The script tests the renderer, generates license notices and builds the Windows
installer into `dist/`. The first build needs internet to download build tools
and dependencies. Docker is only needed for building.

For a direct Windows build, install MSVC C++ Build Tools, then run:

```powershell
npm ci
npm run build:native
```

Regenerate dependency notices if dependencies change. When sharing an installer,
provide its matching corresponding source and third-party notices; see
[release checks](release-checks.md).

The older Python/Docker app remains available through `Start Thermy9 Legacy.cmd`.
