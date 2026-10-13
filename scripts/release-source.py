"""Create a public source snapshot from an explicit allowlist, never the workspace wholesale."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = ['README.md', 'LICENSE', 'NOTICE', '.gitignore', '.dockerignore',
              'package.json', 'package-lock.json', 'Build Native.ps1',
              'Start Thermy9.cmd', 'Start Thermy9 Legacy.cmd', 'setup.ps1']
TREES = {'native/src', 'native/tests', 'native/fonts', 'native/icons', 'native/licenses',
         'scripts', 'src', 'tests', 'web', 'docker'}
NATIVE_FILES = ['Cargo.toml', 'Cargo.lock', 'build.rs', 'tauri.conf.json', 'defaults.json',
                'THIRD-PARTY-NOTICES.txt', 'dependency-licenses.json', 'SOURCE-CODE.txt']

def selected():
    paths = [ROOT / p for p in ROOT_FILES]
    paths += [ROOT / 'native' / p for p in NATIVE_FILES]
    paths += list((ROOT / 'docs').glob('*.md'))
    paths += list((ROOT / 'config').glob('*.example.json'))
    for tree in sorted(TREES):
        paths.extend(p for p in (ROOT / tree).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.log'))
    return sorted(set(paths))

def scan(paths):
    findings = []
    # Compare against actual local settings without copying their contents to the release.
    private_mac = ''
    config = ROOT / 'config/paperang.json'
    if config.exists():
        private_mac = json.loads(config.read_text(encoding='utf-8')).get('macaddress', '')
    patterns = [rb'[A-Za-z]:[\\/]Users[\\/][^\s"<>]+',
                rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'AKIA[0-9A-Z]{16}']
    for path in paths:
        data = path.read_bytes()
        if private_mac and private_mac.encode() in data:
            findings.append(f'{path.relative_to(ROOT)}: personal printer address')
        if any(re.search(pattern, data) for pattern in patterns):
            findings.append(f'{path.relative_to(ROOT)}: private path or credential pattern')
        if path.is_symlink():
            findings.append(f'{path.relative_to(ROOT)}: symlink not allowed')
    if findings:
        raise SystemExit('Release scan failed:\n' + '\n'.join(findings))

def stage(destination):
    destination = destination.resolve()
    if destination.exists():
        raise SystemExit('Use a fresh staging directory; existing files are never removed.')
    paths = selected()
    scan(paths)
    for source in paths:
        target = destination / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    manifest = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in paths}
    (destination / 'SOURCE-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Public snapshot: {len(paths)} reviewed files; private paths, settings, logs and preview images excluded.')

def archive(source, output, vendor=None):
    if output.exists():
        raise SystemExit('Archive already exists; choose a fresh output name.')
    manifest = json.loads((source / 'SOURCE-MANIFEST.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise SystemExit(f'Source changed after staging: {name}')
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6, strict_timestamps=False) as z:
        for name in sorted(manifest):
            z.write(source / name, name)
        z.write(source / 'SOURCE-MANIFEST.json', 'SOURCE-MANIFEST.json')
        if vendor:
            for p in sorted(vendor.rglob('*')):
                if p.is_file():
                    z.write(p, 'vendor/' + str(p.relative_to(vendor)))
            z.writestr('.cargo/config.toml',
                       '[source.crates-io]\nreplace-with = "vendored-sources"\n'
                       '[source.vendored-sources]\ndirectory = "vendor"\n')
    print(f'{output.name}: {output.stat().st_size:,} bytes')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('stage'); s.add_argument('destination', type=Path)
    a = sub.add_parser('archive'); a.add_argument('source', type=Path); a.add_argument('output', type=Path); a.add_argument('--vendor', type=Path)
    args = parser.parse_args()
    if args.command == 'stage': stage(args.destination)
    else: archive(args.source, args.output, args.vendor)
