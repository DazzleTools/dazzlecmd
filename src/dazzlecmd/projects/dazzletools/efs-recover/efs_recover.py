"""
efs-recover - Owner-authorized offline EFS recovery.

Rebuilds a lost EFS certificate's private key from an OLD backup profile --
including the hard case where that backup profile's SID differs from the
current machine (a "defunct / cross SID", e.g. after an OS reinstall) --
then packages it as a .pfx, imports it, and strips EFS from the affected
files so they become plain, portable files.

This is owner-authorized RECOVERY, not an attack: it requires YOUR OWN
backup profile's key material AND YOUR OWN account password. It reuses the
`dpapick3` DPAPI/CryptoAPI engine (no mimikatz, no reimplemented crypto),
runs offline, and never puts a password on a command line.

Privacy: account passwords are supplied ONLY as file paths (--password-file)
and read in-process by the engine; they are never printed, logged, or placed
on a command line. Passing a literal password as an argument is refused.

Typical use (dry-run first; --apply to act):

  dz efs-recover \\
    --backup-profile "\\\\backup-host\\share\\OldPC\\C\\Users\\alice" \\
    --sid S-1-5-21-1111111111-2222222222-3333333333-1001 \\
    --cert A1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4 \\
    --password-file %USERPROFILE%\\pw-candidate-1.txt \\
    --password-file %USERPROFILE%\\pw-candidate-2.txt \\
    --targets "E:\\encrypted-files" \\
    --pfx-out "E:\\keys\\recovered-efs.pfx" \\
    --save-keymaterial "E:\\keys\\keymaterial" \\
    --apply

(All values above are placeholders -- substitute your own backup profile,
its SID, the certificate thumbprint, and your candidate password files.)

The saved .pfx is passwordless by default (rely on the storage location's
own protection); pass --pfx-password-file only to add a wrapper password.

Runs inside this tool's own .venv (created by `dz setup dazzletools:efs-recover`).
Thin CLI over efs_engine; exit codes: 0 ok / 1 error / 2 pending-or-conflict.
"""

import argparse
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import efs_engine as E  # noqa: E402


def build_parser():
    p = argparse.ArgumentParser(
        prog="dz efs-recover",
        description="Owner-authorized offline EFS recovery from a backup profile "
                    "(handles cross/defunct SID). Dry-run by default; --apply to act.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = p.add_argument_group("source (the backup profile holding the lost key)")
    src.add_argument("--backup-profile", metavar="DIR",
                     help="User profile root in the backup (…\\Users\\<name>) or its "
                          "…\\AppData\\Roaming\\Microsoft dir.")
    src.add_argument("--sid", metavar="SID",
                     help="The BACKUP profile's SID (the one its master keys were "
                          "made under -- may differ from this machine's SID).")
    src.add_argument("--cert", metavar="THUMBPRINT",
                     help="Thumbprint of the EFS certificate to recover (40 hex chars, "
                          "spaces ok).")
    src.add_argument("--password-file", metavar="FILE", action="append", default=[],
                     help="File containing a candidate account password (repeatable). "
                          "Read privately; never echoed. Passwords are NOT accepted as "
                          "literal arguments.")

    out = p.add_argument_group("outputs (save the recovered key for reuse)")
    out.add_argument("--pfx-out", metavar="FILE",
                     help="Write the recovered cert+key as a password-protected .pfx "
                          "here (e.g. L:\\Passwords\\Windows\\<cert>.pfx) so future "
                          "recoveries need only this file.")
    out.add_argument("--pfx-password-file", metavar="FILE",
                     help="OPTIONAL file with a password to wrap the saved/imported .pfx. "
                          "If omitted, the .pfx is saved PASSWORDLESS -- rely on the "
                          "storage location's own protection (e.g. an encrypted L: "
                          "container). No random/ephemeral password is ever generated.")
    out.add_argument("--save-keymaterial", metavar="DIR",
                     help="Also copy the raw key material (Protect/RSA/cert folders) here "
                          "for deep archival -- keeps OTHER certs in the profile "
                          "recoverable later. e.g. L:\\Passwords\\Windows\\keymaterial")

    act = p.add_argument_group("actions")
    act.add_argument("--targets", metavar="DIR",
                     help="Directory of EFS files to decrypt + strip after import.")
    act.add_argument("--apply", action="store_true",
                     help="Actually recover/import/decrypt. Without it, dry-run only.")
    act.add_argument("--no-import", action="store_true",
                     help="Recover (and optionally save) the key but do NOT import it "
                          "into this machine's store.")
    act.add_argument("--no-strip", action="store_true",
                     help="Import the key but do NOT decrypt/strip the --targets.")
    return p


def _reject_literal_passwords(argv):
    """Privacy guard: a password must never arrive as a literal CLI value."""
    for a in argv:
        if a in ("--password", "--pfx-password", "-p"):
            print("Error: passwords are accepted only via --password-file / "
                  "--pfx-password-file (never as a literal argument).", file=sys.stderr)
            return False
    return True


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not _reject_literal_passwords(argv):
        return 1
    args = build_parser().parse_args(argv)

    required = {"--backup-profile": args.backup_profile, "--sid": args.sid, "--cert": args.cert}
    missing = [k for k, v in required.items() if not v]
    if missing:
        print("Error: missing required " + ", ".join(missing), file=sys.stderr)
        print("Run 'dz efs-recover --help' for usage.", file=sys.stderr)
        return 1

    km = E.locate(args.backup_profile, args.sid, args.cert)
    problems = E.validate(km)
    print(f"  backup profile : {km.profile_microsoft_dir}")
    print(f"  SID (backup)   : {km.sid}")
    print(f"  certificate    : {km.cert_thumbprint}")
    print(f"  key material   : {'OK' if not problems else 'INCOMPLETE'}")
    for pr in problems:
        print(f"    - {pr}")
    if problems:
        return 1

    ntargets = 0
    if args.targets and os.path.isdir(args.targets):
        ntargets = sum(len(f) for _r, _d, f in os.walk(args.targets))

    if not args.apply:
        print("  MODE           : DRY-RUN (no password read, nothing written/imported)")
        print(f"  would try {len(args.password_file)} candidate password file(s) to unlock the master keys")
        if args.pfx_out:
            print(f"  would save recovered .pfx -> {args.pfx_out}")
        if args.save_keymaterial:
            print(f"  would archive raw key material -> {args.save_keymaterial}")
        if not args.no_import:
            print("  would import the recovered key into Cert:\\CurrentUser\\My")
        if args.targets and not args.no_strip:
            print(f"  would decrypt + strip EFS from {ntargets} file(s) under {args.targets}")
        print("  (re-run with --apply to perform the recovery)")
        return 2

    if not args.password_file:
        print("Error: --apply needs at least one --password-file candidate.", file=sys.stderr)
        return 1

    print("  recovering private key (unlocking master keys with candidate password(s))...")

    def _prog(msg):
        print("    " + msg, flush=True)

    res = E.recover(km, args.password_file, progress=_prog)
    for n in res.notes:
        print(f"    note: {n}")
    if not res.ok:
        print("Error: could not recover the key with the provided password candidate(s).",
              file=sys.stderr)
        print("  Check the SID is the BACKUP profile's SID and that a password from that "
              "era is included.", file=sys.stderr)
        return 1
    print(f"  recovered key from container {res.container_file} "
          f"(password candidate #{res.masterkey_password_index + 1})")

    # Passwordless by default (no random/ephemeral password ever). A wrapper
    # password is used ONLY if the user explicitly supplies one.
    pfx_pw = E.read_secret(args.pfx_password_file) if args.pfx_password_file else None

    try:
        pfx_bytes = E.build_pfx(res.der_cert, res.pem, pfx_pw)
    except Exception as e:
        print(f"Error: failed to assemble .pfx: {e}", file=sys.stderr)
        return 1

    if args.pfx_out:
        outp = Path(args.pfx_out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_bytes(pfx_bytes)
        print(f"  saved recovered .pfx -> {outp}"
              + ("  (password-wrapped)" if args.pfx_password_file
                 else "  (passwordless -- relies on the storage container's own protection)"))

    if args.save_keymaterial:
        _archive_keymaterial(km, args.save_keymaterial)
        print(f"  archived raw key material -> {args.save_keymaterial}")

    if not args.no_import:
        if args.pfx_out:
            # Import straight from the file we just wrote to protected storage --
            # no plaintext-key temp on the local (unprotected) C: drive.
            ok, msg = E.import_pfx_windows(Path(args.pfx_out), pfx_pw)
        else:
            import tempfile
            tmp = Path(tempfile.gettempdir()) / f"_efs_{secrets.token_hex(6)}.pfx"
            tmp.write_bytes(pfx_bytes)
            try:
                ok, msg = E.import_pfx_windows(tmp, pfx_pw)
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass
        if not ok:
            print(f"Error: PFX import failed: {msg}", file=sys.stderr)
            return 1
        print("  imported recovered key into Cert:\\CurrentUser\\My")

    if args.targets and not args.no_strip:
        if args.no_import:
            print("  (skipping decrypt: key was not imported)")
        else:
            ok, msg = E.strip_efs_windows(Path(args.targets))
            total, still = E.verify_decrypted(Path(args.targets))
            print(f"  decrypt+strip: {'OK' if ok else 'reported errors'}; "
                  f"{total - still}/{total} now plaintext"
                  + (f", {still} still encrypted" if still else ""))
            if still:
                print("  WARNING: some files remain encrypted -- review before deleting "
                      "the encrypted-raw safety copy.", file=sys.stderr)
                return 2

    print("  done.")
    return 0


def _archive_keymaterial(km, dest_dir):
    import shutil
    dest = Path(dest_dir)
    pairs = [
        (km.protect_sid_dir, dest / "Protect" / km.sid),
        (km.rsa_sid_dir, dest / "Crypto" / "RSA" / km.sid),
        (km.cert_file.parent, dest / "SystemCertificates" / "My" / "Certificates"),
        (km.protect_dir / "CREDHIST", dest / "Protect" / "CREDHIST"),
    ]
    for src, dst in pairs:
        try:
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for f in src.iterdir():
                    if f.is_file():
                        shutil.copy2(f, dst / f.name)
            elif src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except OSError:
            continue


if __name__ == "__main__":
    sys.exit(main())
