"""Unit tests for efs-recover.

Run in the tool's OWN .venv (has dpapick3 + cryptography):

    .venv\\Scripts\\python -m pytest tests -q

These cover everything testable WITHOUT real DPAPI key material or a Windows
account: encoding-robust password reading, the privacy guard, the KDF
equivalence proof (the perf fix must be bit-identical to dpapick3's original
algorithm), PFX round-trip, and CLI arg/exit-code behavior against a synthetic
key-material tree. The full recovery (real backup profile + password + legacy
CAPI-CSP import + cipher /d) is a human-checklist item -- see tests/checklists/.

The module skips cleanly when dpapick3/cryptography are absent (e.g. under the
dazzlecmd main suite, which does not carry this tool's isolated deps).
"""

import hashlib
import hmac
import os
import struct
import sys

import pytest

pytest.importorskip("dpapick3")
pytest.importorskip("cryptography")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import efs_engine as E       # noqa: E402
import efs_recover as CLI     # noqa: E402


# --------------------------------------------------------------------------
# read_secret: encoding-robust, newline-stripped, meaningful spaces kept
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (b"hunter2\r\n", "hunter2"),                                    # CRLF
    (b"hunter2\n", "hunter2"),                                      # LF
    (b"hunter2", "hunter2"),                                        # no newline
    (b"\xef\xbb\xbfhunter2\n", "hunter2"),                          # UTF-8 BOM
    (b"\xff\xfe" + "hunter2\n".encode("utf-16-le"), "hunter2"),     # UTF-16 LE BOM
    (b"\xfe\xff" + "hunter2\n".encode("utf-16-be"), "hunter2"),     # UTF-16 BE BOM
    (b"pass word \n", "pass word "),                               # trailing space kept
])
def test_read_secret_encodings(tmp_path, raw, expected):
    p = tmp_path / "pw.txt"
    p.write_bytes(raw)
    assert E.read_secret(str(p)) == expected


def test_secret_fingerprint_does_not_reveal_password(tmp_path):
    p = tmp_path / "pw.txt"
    p.write_bytes(b"SuperSecret123\n")
    fp = E.secret_fingerprint(str(p))
    assert "SuperSecret123" not in fp
    assert "chars=14" in fp and "encoding=" in fp


# --------------------------------------------------------------------------
# privacy guard: a literal password must never arrive as a CLI value
# --------------------------------------------------------------------------

def test_reject_literal_passwords():
    assert CLI._reject_literal_passwords(["--password", "x"]) is False
    assert CLI._reject_literal_passwords(["--pfx-password", "x"]) is False
    assert CLI._reject_literal_passwords(["-p", "x"]) is False
    assert CLI._reject_literal_passwords(["--password-file", "f.txt"]) is True


def test_cli_rejects_literal_password():
    assert CLI.main(["--password", "secret"]) == 1


# --------------------------------------------------------------------------
# KDF equivalence: the fast byte-XOR MUST be bit-identical to dpapick3's
# original hex-string algorithm (the load-bearing correctness claim of the
# perf fix). The reference below is dpapick3/crypto.py's exact algorithm.
# --------------------------------------------------------------------------

def _original_pbkdf2(passphrase, salt, keylen, iterations, digest="sha1"):
    h = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}[digest]
    buff = b""
    i = 1
    while len(buff) < keylen:
        U = salt + struct.pack("!L", i)
        i += 1
        derived = hmac.new(passphrase, U, h).digest()
        for _r in range(iterations - 1):
            actual = hmac.new(passphrase, derived, h).digest()
            derived = "".join([chr(int(x, 16) ^ int(y, 16))
                               for (x, y) in zip(derived.hex(), actual.hex())]).encode().hex()
            result = ""
            for j in range(len(derived)):
                if j % 2 == 1:
                    result += derived[j]
            derived = bytes.fromhex(result)
        buff += derived
    return buff[:keylen]


@pytest.mark.parametrize("keylen,iters,digest", [
    (16, 5, "sha1"), (32, 20, "sha1"), (48, 10, "sha256"), (64, 8, "sha512"),
])
def test_faithful_kdf_bit_identical_to_original(keylen, iters, digest):
    for _ in range(5):
        pw, salt = os.urandom(16), os.urandom(16)
        assert E._kdf_faithful(pw, salt, keylen, iters, digest) == \
            _original_pbkdf2(pw, salt, keylen, iters, digest)


def test_standard_and_faithful_kdf_differ():
    # They are DIFFERENT algorithms -- the tool tries both precisely because a
    # given profile may need one or the other (observed in the field).
    pw, salt = b"pw", b"saltsaltsaltsalt"
    assert E._kdf_standard(pw, salt, 32, 10, "sha1") != \
        E._kdf_faithful(pw, salt, 32, 10, "sha1")


# --------------------------------------------------------------------------
# build_pfx: recovered key (PEM) + cert (DER) -> importable PKCS#12
# --------------------------------------------------------------------------

def _throwaway_cert_and_key():
    import datetime
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "efs-test")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(datetime.datetime(2020, 1, 1))
            .not_valid_after(datetime.datetime(2030, 1, 1))
            .sign(key, hashes.SHA256()))
    der = cert.public_bytes(serialization.Encoding.DER)
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.TraditionalOpenSSL,
                            serialization.NoEncryption()).decode()
    return der, pem, key


def test_build_pfx_passwordless_roundtrip():
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
    der, pem, key = _throwaway_cert_and_key()
    pfx = E.build_pfx(der, pem, None)  # passwordless
    k2, c2, _ = pkcs12.load_key_and_certificates(pfx, None)
    assert c2.public_bytes(Encoding.DER) == der
    assert k2.private_numbers().d == key.private_numbers().d


def test_build_pfx_password_wrapped_roundtrip():
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
    der, pem, key = _throwaway_cert_and_key()
    pfx = E.build_pfx(der, pem, "wrap-pw")
    k2, c2, _ = pkcs12.load_key_and_certificates(pfx, b"wrap-pw")
    assert c2.public_bytes(Encoding.DER) == der
    assert k2.private_numbers().d == key.private_numbers().d


# --------------------------------------------------------------------------
# CLI: required-arg validation, dry-run plan + exit codes (synthetic tree)
# --------------------------------------------------------------------------

def _synthetic_profile(tmp_path, sid, thumb, n_targets=1):
    msft = tmp_path / "Microsoft"
    certs = msft / "SystemCertificates" / "My" / "Certificates"
    certs.mkdir(parents=True)
    (certs / thumb).write_bytes(b"\x00")
    (msft / "Protect" / sid).mkdir(parents=True)
    (msft / "Protect" / sid / "mk").write_bytes(b"\x00")
    (msft / "Crypto" / "RSA" / sid).mkdir(parents=True)
    (msft / "Crypto" / "RSA" / sid / "container").write_bytes(b"\x00" * 2000)
    targets = tmp_path / "targets"
    targets.mkdir()
    for i in range(n_targets):
        (targets / f"f{i}.bin").write_bytes(b"x")
    return msft, targets


def test_cli_missing_required_args_exit1():
    assert CLI.main(["--backup-profile", "x"]) == 1  # missing --sid, --cert


def test_cli_incomplete_keymaterial_exit1(tmp_path):
    msft = tmp_path / "Microsoft"
    (msft / "Protect" / "S-1-5-21-1-2-3-1001").mkdir(parents=True)
    rc = CLI.main(["--backup-profile", str(msft), "--sid", "S-1-5-21-1-2-3-1001",
                   "--cert", "A" * 40])
    assert rc == 1  # cert dir / RSA dir absent -> validate() fails


def test_cli_dry_run_reports_plan_exit2(tmp_path, capsys):
    sid, thumb = "S-1-5-21-1-2-3-1001", "A" * 40
    msft, targets = _synthetic_profile(tmp_path, sid, thumb, n_targets=3)
    rc = CLI.main(["--backup-profile", str(msft), "--sid", sid, "--cert", thumb,
                   "--targets", str(targets), "--pfx-out", str(tmp_path / "out.pfx")])
    out = capsys.readouterr().out
    assert rc == 2
    assert "DRY-RUN" in out
    assert "key material   : OK" in out
    assert "would decrypt + strip EFS from 3 file" in out
    assert not (tmp_path / "out.pfx").exists()  # dry-run writes nothing


def test_cli_apply_without_password_file_exit1(tmp_path):
    sid, thumb = "S-1-5-21-1-2-3-1001", "A" * 40
    msft, targets = _synthetic_profile(tmp_path, sid, thumb)
    rc = CLI.main(["--backup-profile", str(msft), "--sid", sid, "--cert", thumb,
                   "--targets", str(targets), "--apply"])
    assert rc == 1  # --apply needs at least one --password-file
