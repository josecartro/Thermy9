# Public-source privacy check

Checked on 2026-10-13, before creating the initial Git history.

The repository was extracted from the reviewed 1.0.1 repository archive into a
new directory. The original working directory, existing account configuration
and any earlier Git history were not imported.

Checks performed:

- Verified the source archive against its per-file SHA-256 manifest.
- No personal email address was found in first-party source or documentation.
- Compared all selected files against the original checkout's printer address
  and existing Git author name/email without copying those values into the repo.
  No matches were found.
- Reviewed account/login/credential strings, local paths and IP-address examples.
  Runtime HTTP tokens are freshly generated, not embedded account credentials.
  Documentation IP examples use the reserved 192.0.2.0/24 range.
- Scanned the public files and initial Git history with Gitleaks 8.30.1 using
  default detection rules and no allowlist exclusions. Reports found no leaks.
- Used a generic contributor identity for the initial commit rather than the
  developer's configured personal email.

Personal printer settings, personal presets, logs, environment files, credentials,
browser profiles, attachments, preview images, dependencies installed locally and
build output are not tracked. Third-party license notices retain their authors'
email addresses and copyright credits; those are not the developer's accounts.

The original archive manifest is retained as a baseline in SOURCE-MANIFEST.json;
publication documentation and privacy hardening can differ from that snapshot.
Git identifies the exact published version. Future changes need their own review.
No automated scan can guarantee detection of every possible secret.
