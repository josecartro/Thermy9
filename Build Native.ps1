param([switch]$SkipTests, [string]$CachePrefix = 'thermy9')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($CachePrefix -notmatch '^[a-z0-9-]+$') { throw 'CachePrefix must contain lowercase letters, digits or hyphens.' }
function Run-NativeCommand([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}
$workspace = $PSScriptRoot.Replace('\', '/')
New-Item -ItemType Directory -Force dist | Out-Null
Run-NativeCommand docker @('build', '-f', 'docker/Dockerfile.native', '-t', 'thermy9-native-builder:local', '.')
$mounts = @('run', '--rm', '--mount', "type=bind,source=$workspace,target=/work",
    '--mount', "type=volume,source=$CachePrefix-native-target,target=/work/native/target",
    '--mount', 'type=volume,source=thermy9-cargo-registry,target=/usr/local/cargo/registry',
    '--mount', 'type=volume,source=thermy9-xwin-cache,target=/xwin',
    '-e', 'XWIN_CACHE_DIR=/xwin', '-e', 'CARGO_BUILD_JOBS=6', 'thermy9-native-builder:local')
if (!$SkipTests) {
    Run-NativeCommand docker ($mounts + @('cargo', 'test', '--locked', '--no-default-features'))
}
Run-NativeCommand docker ($mounts + @('python3', '/work/scripts/native-notices.py'))
Run-NativeCommand docker ($mounts + @('sh', '-c', 'cargo xwin build --locked --release --target x86_64-pc-windows-msvc && cp target/x86_64-pc-windows-msvc/release/thermy9.exe /work/dist/thermy9.exe'))
New-Item -ItemType Directory -Force native/target/x86_64-pc-windows-msvc/release | Out-Null
Copy-Item -LiteralPath dist/thermy9.exe -Destination native/target/x86_64-pc-windows-msvc/release/thermy9.exe
Run-NativeCommand npm.cmd @('ci')
Run-NativeCommand npm.cmd @('run', 'bundle:native')
$appVersion = (Get-Content native/tauri.conf.json -Raw | ConvertFrom-Json).version
$installerName = "Thermy9_${appVersion}_x64-setup.exe"
Copy-Item -LiteralPath "native/target/x86_64-pc-windows-msvc/release/bundle/nsis/$installerName" -Destination dist/
Get-FileHash -LiteralPath "dist/$installerName" -Algorithm SHA256 | Format-List
Write-Host 'Installer and standalone executable are in dist. Docker is only needed for building.'
