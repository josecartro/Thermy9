"""Build-time only: collect notices for locked Windows runtime dependencies."""
import json
from pathlib import Path
import subprocess
from collections import Counter

root = Path(__file__).resolve().parent.parent
metadata = json.loads(subprocess.check_output([
    'cargo', 'metadata', '--locked', '--format-version', '1',
    '--filter-platform', 'x86_64-pc-windows-msvc',
    '--manifest-path', str(root / 'native/Cargo.toml'),
]))
nodes = {node['id']: node for node in metadata['resolve']['nodes']}
packages = {package['id']: package for package in metadata['packages']}
seen = set()

def visit(identifier):
    if identifier in seen:
        return
    seen.add(identifier)
    for dep in nodes[identifier]['deps']:
        if any(kind['kind'] is None for kind in dep['dep_kinds']):
            visit(dep['pkg'])

visit(metadata['resolve']['root'])
parts = ['Thermy9 third-party notices\nGenerated from native/Cargo.lock.\n']
inventory = []
for package in sorted((packages[key] for key in seen), key=lambda p: (p['name'], p['version'])):
    if package['name'] == 'thermy9':
        continue
    directory = Path(package['manifest_path']).parent
    parts.append(f"\n{'=' * 72}\n{package['name']} {package['version']}\n"
                 f"License: {package.get('license') or 'See license below'}\n"
                 f"Source: {package.get('repository') or package.get('source') or ''}\n")
    files = set()
    if package.get('license_file'):
        files.add(directory / package['license_file'])
    for item in directory.iterdir():
        if item.is_file() and item.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT', 'AUTHORS')):
            files.add(item)
        elif item.is_dir() and item.name.lower() in ('license', 'licenses'):
            files.update(p for p in item.rglob('*') if p.is_file())
    for item in sorted(files):
        parts.append(f'\n--- {item.relative_to(directory)} ---\n' + item.read_text(encoding='utf-8', errors='replace'))
    supplemental = root / 'native/licenses' / f"{package['name']}-{package['version']}"
    extra_files = sorted(p for p in supplemental.glob('*') if p.is_file())
    for item in extra_files:
        parts.append(f'\n--- Supplemental upstream notice: {item.name} ---\n' + item.read_text(encoding='utf-8'))
    archive_url = f"https://crates.io/api/v1/crates/{package['name']}/{package['version']}/download"
    parts.append(f'\nExact upstream source archive: {archive_url}\n')
    inventory.append({'name': package['name'], 'version': package['version'],
        'license': package.get('license'), 'source': archive_url,
        'notices': [str(p.relative_to(directory)).replace('\\', '/') for p in sorted(files)] +
                   [f'supplemental/{p.name}' for p in extra_files]})
parts.append('\nBundled DejaVu fonts\n' + (root / 'native/fonts/LICENSE.txt').read_text(encoding='utf-8'))
for license_file in sorted((root / 'src/vendor').glob('*LICENSE*')):
    parts.append('\nPaperang protocol reference attribution\n' + license_file.read_text(encoding='utf-8'))
for license_file in sorted((root / 'native/licenses/installer').glob('*')):
    if license_file.is_file():
        parts.append('\nInstaller/platform component notice: ' + license_file.name + '\n' + license_file.read_text(encoding='utf-8'))
parts.append('''\nMPL-2.0 components in this GPLv3 Larger Work\n
cssparser, cssparser-macros, dtoa-short, option-ext and selectors retain their MPL-2.0
source license and are additionally distributed under GPL-3.0-only as part of
Thermy9, under MPL section 3.3. Existing copyright and license headers are retained.
Their complete source is included in the corresponding-source archive's vendor/
directory, alongside all locked Rust dependencies. See SOURCE-CODE.txt.
''')
(root / 'native/THIRD-PARTY-NOTICES.txt').write_text('\n'.join(parts), encoding='utf-8')
(root / 'native/dependency-licenses.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
print(f'Collected notices for {len(seen)-1} runtime packages and DejaVu fonts.')
print('License expressions:', json.dumps(dict(Counter(p['license'] for p in inventory)), sort_keys=True))
print('Packages without packaged license text:', [p['name'] for p in inventory if not p['notices']])
if any(not p['license'] or not p['notices'] for p in inventory):
    raise SystemExit('Release blocked: a dependency is missing its license declaration or notice text.')
