"""efs_engine -- offline EFS key recovery, engine layer.

Reuses the `dpapick3` DPAPI/CryptoAPI engine (no mimikatz, no hand-rolled
crypto) to rebuild a lost EFS certificate's private key from an OLD backup
profile -- including the case where that profile's SID differs from the
current machine ("defunct/cross SID"). It then packages the recovered
cert+key as a PKCS#12 (.pfx) for import, after which native `cipher /d`
strips EFS from the affected files.

Privacy contract (load-bearing): passwords are accepted ONLY as file paths
and read here, in-process. They are never returned, never logged, never
placed on a command line. `read_secret()` is the single choke point.

Runs inside this tool's own .venv (dpapick3 + cryptography), created by
`dz setup dazzletools:efs-recover`.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import os
import struct as _struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


# dpapick3's shipped pbkdf2 (crypto.py) does a per-round O(n) hex-string XOR
# dance -- hundreds of Python string ops per iteration x thousands of
# iterations x 27 master keys = minutes-to-hours (the wall we hit). We replace
# it with fast equivalents. Two KDFs are provided:
#   - 'standard': plain PBKDF2-HMAC via hashlib (C-accelerated) -- the
#     documented DPAPI master-key KDF, and the fast default.
#   - 'faithful': bit-identical to dpapick's shipped (non-standard XOR-
#     accumulator) algorithm, but with the O(n) hex dance replaced by a byte
#     XOR (verified equivalent: b'\xAB\xCD' ^ b'\x12\x34' == b'\xB9\xF9').
# recover() tries 'standard' first, then 'faithful', so a correct password is
# never missed because of which variant a given master key expects.
_H_ALG = {"sha1": hashlib.sha1, "sha224": hashlib.sha224, "sha256": hashlib.sha256,
          "sha384": hashlib.sha384, "sha512": hashlib.sha512}


def _kdf_standard(passphrase, salt, keylen, iterations, digest="sha1"):
    return hashlib.pbkdf2_hmac(digest, passphrase, salt, iterations, keylen)[:keylen]


def _kdf_faithful(passphrase, salt, keylen, iterations, digest="sha1"):
    h = _H_ALG.get(digest, hashlib.sha1)
    buff = b""
    i = 1
    while len(buff) < keylen:
        U = salt + _struct.pack("!L", i)
        i += 1
        derived = _hmac.new(passphrase, U, h).digest()
        for _r in range(iterations - 1):
            actual = _hmac.new(passphrase, derived, h).digest()
            derived = bytes(a ^ b for a, b in zip(derived, actual))
        buff += derived
    return buff[:keylen]


_KDFS = {"standard": _kdf_standard, "faithful": _kdf_faithful}


def set_kdf(mode: str) -> None:
    """Point dpapick3.crypto.pbkdf2 at one of our fast KDFs (idempotent;
    no-op if dpapick3 is absent)."""
    try:
        import dpapick3.crypto as _c
    except Exception:
        return
    _c.pbkdf2 = _KDFS.get(mode, _kdf_standard)


set_kdf("standard")


# --- privacy choke point -----------------------------------------------------

def read_secret(path: str) -> str:
    """Read a password from a file, encoding-robust, stripped of a trailing
    newline only (a real password may end in spaces, so those are kept).

    Detects a UTF-8/UTF-16 BOM -- a password file saved by Notepad as UTF-16
    would otherwise decode to garbage under UTF-8 and silently fail every
    unlock. The ONLY place a password enters the process; the string never
    leaves this module except into dpapick3's decrypt calls. Never printed
    or logged.
    """
    raw = Path(path).read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        s = raw[3:].decode("utf-8")
    elif raw[:2] == b"\xff\xfe":
        s = raw[2:].decode("utf-16-le")
    elif raw[:2] == b"\xfe\xff":
        s = raw[2:].decode("utf-16-be")
    else:
        s = raw.decode("utf-8")
    return s.rstrip("\r\n")


def secret_fingerprint(path: str) -> str:
    """A NON-revealing description of a password file for diagnostics:
    detected encoding + character count + a short salted hash prefix. Never
    exposes the password itself."""
    raw = Path(path).read_bytes()
    enc = ("utf16-le" if raw[:2] == b"\xff\xfe" else
           "utf16-be" if raw[:2] == b"\xfe\xff" else
           "utf8-bom" if raw[:3] == b"\xef\xbb\xbf" else "utf8/ascii")
    s = read_secret(path)
    tag = hashlib.sha256(("efs-diag:" + s).encode("utf-8")).hexdigest()[:8]
    return f"encoding={enc} chars={len(s)} sha256[:8]={tag}"


# --- inputs / results --------------------------------------------------------

@dataclass
class KeyMaterial:
    profile_microsoft_dir: Path      # ...\AppData\Roaming\Microsoft
    sid: str                         # the BACKUP profile's SID (may be defunct)
    cert_thumbprint: str             # uppercase, no separators
    cert_file: Path                  # SystemCertificates\My\Certificates\<thumbprint>
    protect_dir: Path                # Protect\  (holds CREDHIST)
    protect_sid_dir: Path            # Protect\<SID>\  (master keys)
    rsa_sid_dir: Path                # Crypto\RSA\<SID>\ (CAPI containers)


@dataclass
class RecoveryResult:
    ok: bool
    pem: Optional[str] = None        # RSA private key PEM (sensitive; not logged)
    der_cert: Optional[bytes] = None
    container_file: Optional[str] = None
    masterkey_password_index: Optional[int] = None  # which candidate worked
    notes: List[str] = field(default_factory=list)


# --- locate ------------------------------------------------------------------

def locate(profile_dir: str, sid: str, cert_thumbprint: str) -> KeyMaterial:
    """Resolve the key-material paths under a backup profile.

    ``profile_dir`` is the user profile root (…\\Users\\Extreme), OR its
    …\\AppData\\Roaming\\Microsoft directory -- both are accepted.
    """
    p = Path(profile_dir)
    msft = p if p.name.lower() == "microsoft" else p / "AppData" / "Roaming" / "Microsoft"
    thumb = cert_thumbprint.upper().replace(" ", "")
    km = KeyMaterial(
        profile_microsoft_dir=msft,
        sid=sid,
        cert_thumbprint=thumb,
        cert_file=msft / "SystemCertificates" / "My" / "Certificates" / thumb,
        protect_dir=msft / "Protect",
        protect_sid_dir=msft / "Protect" / sid,
        rsa_sid_dir=msft / "Crypto" / "RSA" / sid,
    )
    return km


def validate(km: KeyMaterial) -> List[str]:
    """Return a list of human-readable problems (empty == all present)."""
    problems = []
    if not km.cert_file.is_file():
        problems.append(f"certificate {km.cert_thumbprint} not found at {km.cert_file}")
    if not km.protect_sid_dir.is_dir():
        problems.append(f"master keys dir missing: {km.protect_sid_dir}")
    if not km.rsa_sid_dir.is_dir():
        problems.append(f"RSA container dir missing: {km.rsa_sid_dir}")
    return problems


# --- cert parse (via dpapick3 Cert probe) ------------------------------------

def parse_cert(cert_file: Path) -> Tuple[Optional[bytes], Optional[str]]:
    """Return (der_certificate_bytes, key_container_name) from a Windows
    SystemCertificates store file. Either may be None if absent."""
    from dpapick3.probes.certificate import Cert
    data = cert_file.read_bytes()
    c = Cert(data)
    der = getattr(c, "certificate", None)
    keyname = getattr(c, "name", None)
    return der, keyname


def cert_modulus(der_cert: bytes) -> Optional[int]:
    """Public-key modulus of the certificate (to match the right container)."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import rsa
        cert = x509.load_der_x509_certificate(der_cert)
        pub = cert.public_key()
        if isinstance(pub, rsa.RSAPublicKey):
            return pub.public_numbers().n
    except Exception:
        return None
    return None


# --- unwrap master keys + recover the RSA private key ------------------------

def unlock_pool(km: KeyMaterial, password: str):
    """Build a MasterKeyPool for the backup SID and unlock its master keys
    with ``password`` (directly via ``decryptWithPassword`` on each key --
    the path proven to work; ``try_credential`` + a pool-level count proved
    unreliable because ``mkp.keys[guid]`` is a LIST of MasterKeyFile). Returns
    the pool if at least one key decrypted, else None. ``password`` never
    logged."""
    from dpapick3.masterkey import MasterKeyPool
    mkp = MasterKeyPool()
    mkp.loadDirectory(str(km.protect_sid_dir))
    credhist = km.protect_dir / "CREDHIST"
    if credhist.is_file():
        try:
            mkp.addCredhistFile(km.sid, str(credhist))
        except Exception:
            pass  # CREDHIST is best-effort; direct password may still work
    if _count_decrypted(mkp, km.sid, password) > 0:
        return mkp
    return None


def _count_decrypted(mkp, sid: str, password: str) -> int:
    """Decrypt every master key in the pool with ``password`` and return how
    many succeeded. ``mkp.keys[guid]`` is a list of MasterKeyFile."""
    n = 0
    for _guid, mkl in getattr(mkp, "keys", {}).items():
        for mkf in (mkl if isinstance(mkl, list) else [mkl]):
            try:
                mkf.decryptWithPassword(sid, password)
                if getattr(mkf, "decrypted", False):
                    n += 1
                    break
            except Exception:
                continue
    return n


def _candidate_containers(rsa_sid_dir: Path, min_size: int = 1000) -> List[Path]:
    """Real CAPI private-key blobs are the larger files; the many tiny (~88B)
    entries are signature/metadata. Filter to plausible key blobs so we do not
    attempt DPAPI decrypt on thousands of non-keys."""
    out = []
    for f in rsa_sid_dir.iterdir():
        try:
            if f.is_file() and f.stat().st_size >= min_size:
                out.append(f)
        except OSError:
            continue
    # Larger first -- the export-flags+key blobs tend to be the biggest.
    out.sort(key=lambda p: p.stat().st_size, reverse=True)
    return out


def recover_pem(km: KeyMaterial, mkp, password: str, want_modulus: Optional[int],
                progress=None) -> Optional[Tuple[str, str]]:
    """Try candidate RSA containers until one decrypts and (if we know the
    cert modulus) matches the certificate's public key. Returns
    (pem, container_filename) or None. ``password`` never logged."""
    from dpapick3.probes.certificate import PrivateKeyBlob
    cands = _candidate_containers(km.rsa_sid_dir)
    if progress:
        progress(f"scanning {len(cands)} candidate RSA container(s)")
    for i, cf in enumerate(cands):
        if progress and i and i % 25 == 0:
            progress(f"  ...{i}/{len(cands)} containers tried")
        try:
            pk = PrivateKeyBlob(cf.read_bytes())
        except Exception:
            continue
        try:
            if not pk.try_decrypt_with_password(password, mkp, km.sid):
                continue
            pem = pk.export()
            if not pem:
                continue
        except Exception:
            continue
        if want_modulus is not None:
            if _pem_modulus(pem) != want_modulus:
                continue  # decrypted a different key; keep looking
        return pem, cf.name
    return None


def _pem_modulus(pem: str) -> Optional[int]:
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        key = load_pem_private_key(pem.encode(), password=None)
        return key.public_key().public_numbers().n
    except Exception:
        return None


def recover(km: KeyMaterial, password_files: List[str], progress=None) -> RecoveryResult:
    """Full recovery: parse cert, then for each candidate password (read
    privately from file) try to unlock the master keys and decrypt the RSA
    container that matches the certificate. ``progress`` (if given) receives
    short status strings -- never a password."""
    problems = validate(km)
    if problems:
        return RecoveryResult(ok=False, notes=problems)
    der, keyname = parse_cert(km.cert_file)
    want_n = cert_modulus(der) if der else None
    notes = []
    if der is None:
        notes.append("warning: could not extract DER certificate from store file")
    # Try the fast standard KDF first, then dpapick's faithful KDF -- some
    # profiles' master keys unlock only under the latter (observed: this
    # W7-era profile). A correct password must never be missed on KDF choice.
    for kdf_mode in ("standard", "faithful"):
        set_kdf(kdf_mode)
        if progress:
            progress(f"KDF={kdf_mode}")
        unlocked_any = False
        for idx, pwfile in enumerate(password_files):
            password = read_secret(pwfile)  # sensitive; not logged
            if progress:
                progress(f"  password candidate #{idx + 1}: unlocking master keys...")
            mkp = unlock_pool(km, password)
            if mkp is None:
                continue
            unlocked_any = True
            got = recover_pem(km, mkp, password, want_n, progress=progress)
            if got is None:
                notes.append(f"password #{idx + 1} ({kdf_mode}): master keys unlocked "
                             f"but no matching RSA container")
                continue
            pem, container = got
            return RecoveryResult(ok=True, pem=pem, der_cert=der, container_file=container,
                                  masterkey_password_index=idx, notes=notes)
        if unlocked_any:
            break  # this KDF decrypts keys; the other won't do better
        if kdf_mode == "standard":
            notes.append("no master key unlocked with standard KDF; retried with faithful KDF")
    return RecoveryResult(ok=False, notes=notes)


# --- package + import + strip (Windows side) ---------------------------------

def build_pfx(der_cert: bytes, pem: str, pfx_password: Optional[str]) -> bytes:
    """Assemble a PKCS#12 from the recovered key + cert.

    ``pfx_password`` is OPTIONAL. When None/empty the PFX is written
    PASSWORDLESS (NoEncryption) -- appropriate when the storage location is
    itself an encrypted container (e.g. an encrypted L: drive), and it avoids
    a random/ephemeral password that could never be reproduced. Supply a
    password only if you want a second at-rest wrapper.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import (
        load_pem_private_key, pkcs12, BestAvailableEncryption, NoEncryption,
    )
    cert = x509.load_der_x509_certificate(der_cert)
    key = load_pem_private_key(pem.encode(), password=None)
    enc = BestAvailableEncryption(pfx_password.encode()) if pfx_password else NoEncryption()
    return pkcs12.serialize_key_and_certificates(
        name=b"efs-recover",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=enc,
    )


#: Legacy CryptoAPI provider EFS uses for XP/Server-2003-compatibility files.
EFS_LEGACY_CSP = "Microsoft Enhanced Cryptographic Provider v1.0"


def import_pfx_windows(pfx_path: Path, pfx_password: Optional[str]) -> Tuple[bool, str]:
    """Import a .pfx into CurrentUser\\My **in a legacy CAPI CSP** via certutil.

    This is load-bearing: EFS files at the "Windows XP/Server 2003"
    compatibility level require the private key in a CryptoAPI provider. A
    CNG/KSP import (PowerShell ``Import-PfxCertificate``'s default) leaves the
    key present-and-accessible yet UNUSABLE by EFS -- ``cipher /c`` reports
    "Key information cannot be retrieved" and decryption fails. Forcing
    ``-csp EFS_LEGACY_CSP`` fixes it (verified: the same file that failed
    under CNG decrypted immediately after a CAPI import).

    A passwordless PFX imports with ``-p ""`` (no secret on the command line);
    a caller-supplied wrapper password is passed via ``-p`` (that ephemeral
    wrapper -- never the account password -- is the only value on argv, and
    only when explicitly requested)."""
    if sys.platform != "win32":
        return False, "PFX import is Windows-only"
    cmd = ["certutil", "-user", "-f", "-p", pfx_password or "", "-csp", EFS_LEGACY_CSP,
           "-importpfx", "My", str(pfx_path), "NoChain,NoRoot"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and "completed successfully" in (r.stdout or ""):
            return True, "imported (legacy CAPI CSP)"
        return False, ((r.stderr or "") + (r.stdout or "")).strip()[-400:]
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def strip_efs_windows(target_dir: Path) -> Tuple[bool, str]:
    """Decrypt + remove EFS from every file under target_dir (`cipher /d /s`)."""
    if sys.platform != "win32":
        return False, "EFS strip is Windows-only"
    r = subprocess.run(["cipher", "/d", "/s:" + str(target_dir)],
                       capture_output=True, text=True)
    # cipher returns 0 even with per-file notes; treat nonzero as failure.
    return (r.returncode == 0), (r.stdout or r.stderr).strip()[-500:]


def verify_decrypted(target_dir: Path) -> Tuple[int, int]:
    """Return (total_files, still_encrypted) under target_dir."""
    FILE_ATTRIBUTE_ENCRYPTED = 0x4000
    total = enc = 0
    for root, _dirs, files in os.walk(target_dir):
        for name in files:
            total += 1
            try:
                attrs = os.stat(os.path.join(root, name)).st_file_attributes  # type: ignore[attr-defined]
                if attrs & FILE_ATTRIBUTE_ENCRYPTED:
                    enc += 1
            except OSError:
                continue
    return total, enc
