# Release checks — 1.0.1

Source is public. The Windows installer remains a local release candidate pending a fresh-PC test.

## License review

The owner selected GPLv3. Original Thermy9 code, documentation and original icons
are GPL-3.0-only; LICENSE contains the complete GNU text. Existing dependency
licenses are preserved. Native dependency declarations and packaged license texts
were reviewed for the Windows x64 runtime dependency graph (304 packages,
including some compile-time macro dependencies). See native/dependency-licenses.json.

The declared licenses are MIT, Apache-2.0, BSD-2/3-Clause, Zlib, Unicode-3.0,
MPL-2.0, and permissive alternatives such as 0BSD/Unlicense. No unlicensed runtime
crate declaration was found. Six crates omitted standalone license texts from
their published crate packages; supplemental copies have been added. Five use
license text from their exact recorded upstream commit. selectors uses Mozilla's
canonical MPL text because the upstream repository also lacks a standalone copy.
URLs and hashes are recorded in native/licenses/provenance.json.

Five dependencies use MPL-2.0: cssparser, cssparser-macros, dtoa-short, option-ext
and selectors. Their inspected source headers contain no secondary-license
incompatibility notice. Existing notices remain, and the Larger Work notice
additionally distributes these sources under GPLv3 as required by MPL 3.3.
The corresponding-source archive includes all locked Rust dependency sources.
Do not distribute the installer without providing matching source access.

The six DejaVu fonts are unmodified and retain the Bitstream Vera/DejaVu notice.
The GPL paragraph for debian/* in Debian's copyright file does not apply to the
font files. Paperang reference notices are MIT and retained. NSIS and its Tauri
plugin have separate retained notices. Microsoft's Windows/WebView2 components
remain under Microsoft's platform terms, not Thermy9's license.

This is a dependency/provenance review, not a legal opinion or patent/trademark
clearance. Product compatibility names do not imply manufacturer endorsement.

References:
- https://www.gnu.org/licenses/gpl-3.0.html — source distribution and system libraries
- https://www.gnu.org/licenses/license-list.html — GPL-compatible license guidance
- https://www.mozilla.org/en-US/MPL/2.0/FAQ/#q14 — MPL/GPL Larger Works
- https://www.apache.org/licenses/LICENSE-2.0 — Apache redistribution requirements
- https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution

## Public files

scripts/release-source.py builds from an explicit allowlist. Personal config JSON,
logs, virtual environments, node_modules, build output, upstream checkouts,
preview images and Git history are excluded. Printer-address examples are now
AA:BB:CC:DD:EE:FF. config/*.example.json contains no user's settings.
The script checks selected files for the actual local printer address, Windows
user paths and common credential patterns. Such scans reduce risk but are not a
guarantee against every possible secret. Runtime authentication tokens in the
legacy HTTP app are generated at startup, not shipped credentials.

## Build and distribution

Cargo.lock and package-lock.json pin application dependencies. The Linux Rust
builder image digest and cargo-xwin version are pinned. The build uses --locked
and npm ci; a fresh target-cache prefix can verify a clean compilation.
SDK/apt downloads, timestamps and installer tooling mean byte-identical builds
are not claimed. Publish the tested installer, matching source archive and SHA256
checksums together; never infer reproducibility from matching version numbers.

The source archive includes vendor/ and a Cargo source-replacement configuration.
The smaller repository archive excludes vendor/ and can be used to start a clean
public Git repository. Neither archive contains existing Git history.

## Fresh-PC test — assigned to the owner

Use the 1.0.1 installer on the other Windows 10/11 x64 PC:

1. Install with security enabled; record any block or WebView2 prerequisite issue.
2. Open from Start without Python or Docker installed.
3. Find the powered-on printer and check its status.
4. Preview and print one machine label, a four-column flag and an image.
5. Export/import a personal preset; close/reopen and check it is still available.
6. Check uninstall from Windows Installed apps. Keep the preset export first.

Record the Windows version, printer model and any error text. No physical print
was sent as part of this source-release review. Earlier hardware results remain
documented separately in validation.md; the fresh-PC result is pending.
