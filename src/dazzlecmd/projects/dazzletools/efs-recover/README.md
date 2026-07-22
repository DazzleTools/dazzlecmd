# efs-recover

Owner-authorized **offline EFS recovery**: rebuild a lost EFS certificate's private key from an OLD backup profile — including the hard case where the backup profile's account SID differs from the current machine (a "defunct / cross SID", e.g. after an OS reinstall) — then import it and strip EFS from the affected files so they become plain, portable files.

This is recovery for **your own** data: it requires your own backup profile's key material AND your own account password. It reuses the [`dpapick3`](https://pypi.org/project/dpapick3/) DPAPI/CryptoAPI engine (no mimikatz, no reimplemented crypto), runs offline, and never puts a password on a command line.

## When you'd use this

Windows EFS ("green filenames" per-file encryption) locks files to a certificate whose private key lives in your profile. If that certificate is lost from your live store and there's no Data Recovery Agent, the files can't be opened — even as admin, even on another PC. If a **backup of the old profile** survives (the cert, the `Crypto\RSA` key container, the `Protect` DPAPI master keys) and you know an account password from that era, this tool rebuilds the key offline and decrypts the files.

## Setup

Runs in its own isolated venv (dpapick3 + cryptography):

```
dz setup dazzletools:efs-recover
```

## Usage

Dry-run first (validates the key material, writes nothing); add `--apply` to act. All values are placeholders:

```
dz efs-recover \
  --backup-profile "\\backup-host\share\OldPC\C\Users\alice" \
  --sid S-1-5-21-1111111111-2222222222-3333333333-1001 \
  --cert A1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4 \
  --password-file %USERPROFILE%\pw-candidate-1.txt \
  --password-file %USERPROFILE%\pw-candidate-2.txt \
  --targets "E:\encrypted-files" \
  --pfx-out "E:\keys\recovered-efs.pfx" \
  --apply
```

- Point `--backup-profile` at the profile root (`…\Users\<name>`) or its `…\AppData\Roaming\Microsoft`. Use a **local** copy of the key material — the DPAPI unlock reads many small files, and a slow network share crawls.
- `--sid` is the **backup** profile's SID (its master keys are bound to it), not the current machine's.
- Passwords are supplied only as file paths and read in-process; they are never printed, logged, or placed on a command line. Add several candidates — the tool tries each, under both KDFs (see below). A literal `--password` argument is refused.
- The saved `.pfx` is passwordless by default (rely on the storage location's own protection); `--pfx-password-file` adds a wrapper. `--save-keymaterial <dir>` archives the raw components for future/other-cert recovery.

Exit codes: `0` ok · `1` error · `2` pending (dry-run with work) or conflicts.

## Notes on the mechanics

- **KDF fallback**: DPAPI master-key derivation is tried with a standard PBKDF2 first, then dpapick3's own variant — some profiles unlock only under the latter. A correct password is never missed on KDF choice.
- **Legacy CSP**: keys are imported into a CryptoAPI provider via `certutil -csp "Microsoft Enhanced Cryptographic Provider v1.0"`. XP/Server-2003-compatibility EFS files require this; a modern CNG/KSP import leaves the key present but unusable by EFS.
- **Cross-platform split**: the offline unwrap is portable; the PFX import and `cipher /d` strip are Windows-only.

## Architecture

Thin CLI (`efs_recover.py`) over an engine module (`efs_engine.py`): the engine reuses dpapick3 for the DPAPI/CAPI crypto and `cryptography` for PKCS#12 assembly; the CLI owns argument parsing, the password-privacy guard, dry-run/apply, and exit codes.

## Development

```
.venv\Scripts\python -m pytest tests -q
```

Unit tests cover the deps-available logic (encoding-robust password reading, the privacy guard, the KDF-equivalence proof, PFX round-trip, CLI exit codes). The full recovery — real backup profile, real password, legacy-CSP import, `cipher /d` — is a human checklist (`tests/checklists/` in the aggregator).

## Files

- `.dazzlecmd.json` — tool manifest (its own `.venv` + `dz_setup.py`)
- `efs_recover.py` — CLI entry point (`main(argv=None)`)
- `efs_engine.py` — recovery engine (locate → unwrap → decrypt container → build PFX → import → strip)
- `requirements.txt` — `dpapick3`, `cryptography` (installed into `.venv` by `dz setup`)
- `tests/` — unit tests (run in the tool's venv)
