"""Tests for projects/core/find/dz_setup.py installer-selection logic.

This is the real-world validator for v0.7.46's setup-script API. The
tests construct fake PlatformInfo values and verify that select_installer
picks the right command per OS + distro family. shutil.which is mocked
so the tests don't depend on which package managers happen to be
installed on the test machine.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from unittest.mock import patch

import pytest

from dazzlecmd_lib.platform_detect import PlatformInfo


# Load projects/core/find/dz_setup.py as a module so we can call
# select_installer() directly with synthetic PlatformInfo values.
_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.dirname(_HERE)
_FIND_SETUP = os.path.join(_REPO_ROOT, "projects", "core", "find", "dz_setup.py")


@pytest.fixture(scope="module")
def find_setup():
    spec = importlib.util.spec_from_file_location("find_setup", _FIND_SETUP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pi(os_name, subtype=None, id_like=(), arch="x86_64", is_wsl=False, version=None):
    return PlatformInfo(
        os=os_name,
        subtype=subtype,
        arch=arch,
        is_wsl=is_wsl,
        version=version,
        id_like=tuple(id_like),
    )


class TestWindowsInstallerSelection:
    def test_winget_preferred(self, find_setup):
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda n: (
                f"/fake/{n}.exe" if n in ("winget", "scoop", "choco") else None
            )
            cmd, reason = find_setup.select_installer(_pi("windows", "win11"))
        assert cmd[0] == "winget"
        assert "sharkdp.fd" in cmd
        assert "winget" in reason

    def test_scoop_when_no_winget(self, find_setup):
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda n: (
                f"/fake/{n}" if n in ("scoop", "choco") else None
            )
            cmd, reason = find_setup.select_installer(_pi("windows", "win11"))
        assert cmd[0] == "scoop"
        assert cmd == ["scoop", "install", "fd"]

    def test_choco_when_no_winget_no_scoop(self, find_setup):
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda n: f"/fake/{n}" if n == "choco" else None
            cmd, reason = find_setup.select_installer(_pi("windows", "win11"))
        assert cmd[0] == "choco"
        assert cmd == ["choco", "install", "-y", "fd"]

    def test_none_when_no_installer(self, find_setup):
        with patch("shutil.which", return_value=None):
            cmd, reason = find_setup.select_installer(_pi("windows", "win11"))
        assert cmd is None
        assert "winget" in reason and "scoop" in reason and "choco" in reason


class TestMacosInstallerSelection:
    def test_brew_when_present(self, find_setup):
        with patch("shutil.which", return_value="/usr/local/bin/brew"):
            cmd, reason = find_setup.select_installer(_pi("macos", "macos14"))
        assert cmd == ["brew", "install", "fd"]

    def test_none_when_no_brew(self, find_setup):
        with patch("shutil.which", return_value=None):
            cmd, reason = find_setup.select_installer(_pi("macos", "macos14"))
        assert cmd is None
        assert "brew.sh" in reason or "Homebrew" in reason


class TestLinuxInstallerSelection:
    """Linux dispatch uses pi.id_like for distro-family decisions so
    Ubuntu/Mint/Kali all route through apt-get without enumeration."""

    def test_debian_uses_apt_get(self, find_setup):
        with patch("os.geteuid", return_value=0, create=True):
            cmd, reason = find_setup.select_installer(
                _pi("linux", "debian", ("debian",))
            )
        assert cmd == ["apt-get", "install", "-y", "fd-find"]
        assert "fdfind" in reason  # documented binary-name quirk

    def test_ubuntu_via_id_like_debian(self, find_setup):
        """Ubuntu has subtype='ubuntu' AND id_like includes 'debian'."""
        with patch("os.geteuid", return_value=0, create=True):
            cmd, _ = find_setup.select_installer(
                _pi("linux", "ubuntu", ("ubuntu", "debian"))
            )
        assert cmd == ["apt-get", "install", "-y", "fd-find"]

    def test_linux_mint_via_id_like_debian(self, find_setup):
        with patch("os.geteuid", return_value=0, create=True):
            cmd, _ = find_setup.select_installer(
                _pi("linux", "linuxmint", ("linuxmint", "ubuntu", "debian"))
            )
        assert cmd == ["apt-get", "install", "-y", "fd-find"]

    def test_fedora_uses_dnf(self, find_setup):
        # Tier 1 rhel-family branch checks shutil.which("dnf") to pick
        # between dnf and yum; mock dnf as present.
        with patch("os.geteuid", return_value=0, create=True), \
             patch("shutil.which", side_effect=lambda n: f"/usr/bin/{n}" if n == "dnf" else None):
            cmd, _ = find_setup.select_installer(
                _pi("linux", "fedora", ("fedora",))
            )
        assert cmd == ["dnf", "install", "-y", "fd-find"]

    def test_centos_stream_via_id_like_rhel(self, find_setup):
        with patch("os.geteuid", return_value=0, create=True), \
             patch("shutil.which", side_effect=lambda n: f"/usr/bin/{n}" if n == "dnf" else None):
            cmd, _ = find_setup.select_installer(
                _pi("linux", "centos", ("centos", "rhel", "fedora"))
            )
        assert cmd == ["dnf", "install", "-y", "fd-find"]

    def test_arch_uses_pacman(self, find_setup):
        with patch("os.geteuid", return_value=0, create=True):
            cmd, _ = find_setup.select_installer(
                _pi("linux", "arch", ("arch",))
            )
        assert cmd == ["pacman", "-S", "--noconfirm", "fd"]

    def test_manjaro_via_id_like_arch(self, find_setup):
        with patch("os.geteuid", return_value=0, create=True):
            cmd, _ = find_setup.select_installer(
                _pi("linux", "manjaro", ("manjaro", "arch"))
            )
        assert cmd == ["pacman", "-S", "--noconfirm", "fd"]

    def test_alpine_uses_apk(self, find_setup):
        with patch("os.geteuid", return_value=0, create=True):
            cmd, _ = find_setup.select_installer(
                _pi("linux", "alpine", ("alpine",))
            )
        assert cmd == ["apk", "add", "fd"]

    def test_opensuse_uses_zypper(self, find_setup):
        with patch("os.geteuid", return_value=0, create=True):
            cmd, _ = find_setup.select_installer(
                _pi("linux", "opensuse-leap", ("opensuse-leap", "suse"))
            )
        assert cmd == ["zypper", "install", "-y", "fd"]

    def test_solus_uses_eopkg(self, find_setup):
        """Solus declares ID=solus with no ID_LIKE (independent distro)."""
        with patch("os.geteuid", return_value=0, create=True):
            cmd, reason = find_setup.select_installer(
                _pi("linux", "solus", ("solus",))
            )
        assert cmd == ["eopkg", "install", "-y", "fd"]
        assert "eopkg" in reason
        assert "binary-detect" not in reason  # Tier 1, not fallback

    def test_sudo_prepended_when_not_root(self, find_setup):
        with patch("os.geteuid", return_value=1000, create=True):
            cmd, reason = find_setup.select_installer(
                _pi("linux", "debian", ("debian",))
            )
        assert cmd[0] == "sudo"
        assert "sudo" in reason

    def test_unsupported_linux_returns_none_when_no_pm(self, find_setup):
        """Tier 1 (id_like) doesn't match AND Tier 2 (PM binary detection)
        finds nothing on PATH -> clean failure with manual-install hint."""
        with patch("os.geteuid", return_value=0, create=True), \
             patch("shutil.which", return_value=None):
            cmd, reason = find_setup.select_installer(
                _pi("linux", "voidlinux", ("voidlinux",))
            )
        assert cmd is None
        assert "voidlinux" in reason
        assert "manual" in reason.lower() or "github" in reason.lower()


class TestLinuxTier2BinaryDetectionFallback:
    """v0.7.46: Tier 2 fallback uses shutil.which() to detect a package
    manager when id_like doesn't match a known family. Covers distros
    that fail to declare ID_LIKE properly (Void, NixOS, Gentoo, or
    one-off bespoke distros)."""

    def _which_only(self, pm_name):
        """Mock factory: shutil.which returns truthy ONLY for pm_name."""
        return lambda n: f"/usr/bin/{n}" if n == pm_name else None

    def test_void_uses_xbps_via_fallback(self, find_setup):
        """Void Linux: subtype=void, ID_LIKE=(none). Tier 1 misses;
        Tier 2 detects xbps-install."""
        with patch("os.geteuid", return_value=0, create=True), \
             patch("shutil.which", side_effect=self._which_only("xbps-install")):
            cmd, reason = find_setup.select_installer(
                _pi("linux", "void", ("void",))
            )
        assert cmd == ["xbps-install", "-S", "-y", "fd"]
        assert "binary-detect" in reason or "Void" in reason

    def test_nixos_uses_nix_env_via_fallback(self, find_setup):
        with patch("os.geteuid", return_value=0, create=True), \
             patch("shutil.which", side_effect=self._which_only("nix-env")):
            cmd, reason = find_setup.select_installer(
                _pi("linux", "nixos", ("nixos",))
            )
        assert cmd == ["nix-env", "-iA", "nixpkgs.fd"]
        assert "NixOS" in reason

    def test_unknown_solus_derivative_falls_back_to_eopkg(self, find_setup):
        """A hypothetical Solus derivative that doesn't declare ID_LIKE
        still routes through eopkg via the Tier 2 binary-detection
        fallback when only eopkg is on PATH."""
        with patch("os.geteuid", return_value=0, create=True), \
             patch("shutil.which", side_effect=self._which_only("eopkg")):
            cmd, reason = find_setup.select_installer(
                _pi("linux", "solusderiv", ("solusderiv",))
            )
        assert cmd == ["eopkg", "install", "-y", "fd"]
        assert "Solus" in reason or "binary-detect" in reason

    def test_gentoo_tier1_uses_emerge(self, find_setup):
        """Gentoo declares ID=gentoo in some configs and matches Tier 1
        directly (no fallback needed)."""
        with patch("os.geteuid", return_value=0, create=True):
            cmd, reason = find_setup.select_installer(
                _pi("linux", "gentoo", ("gentoo",))
            )
        assert cmd == ["emerge", "--ask=n", "sys-apps/fd"]
        assert "emerge" in reason
        assert "binary-detect" not in reason  # Tier 1, not fallback

    def test_bespoke_distro_with_apt_falls_back(self, find_setup):
        """A bespoke distro that ships apt-get but doesn't declare
        debian-family in ID_LIKE: Tier 2 still routes through apt-get."""
        with patch("os.geteuid", return_value=0, create=True), \
             patch("shutil.which", side_effect=self._which_only("apt-get")):
            cmd, reason = find_setup.select_installer(
                _pi("linux", "weirddistro", ("weirddistro",))
            )
        assert cmd == ["apt-get", "install", "-y", "fd-find"]
        assert "binary-detect" in reason

    def test_rhel_family_prefers_dnf_over_yum(self, find_setup):
        """Within Tier 1 rhel-family branch: dnf wins when both are on
        PATH (matches what modern RHEL/Fedora/CentOS-Stream users expect)."""
        with patch("os.geteuid", return_value=0, create=True), \
             patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda n: (
                f"/usr/bin/{n}" if n in ("dnf", "yum") else None
            )
            cmd, _ = find_setup.select_installer(
                _pi("linux", "rhel", ("rhel", "fedora"))
            )
        assert cmd[0] == "dnf"

    def test_rhel_family_falls_back_to_yum_on_legacy(self, find_setup):
        """RHEL/CentOS 7-era: only yum is on PATH, not dnf."""
        with patch("os.geteuid", return_value=0, create=True), \
             patch("shutil.which", side_effect=self._which_only("yum")):
            cmd, reason = find_setup.select_installer(
                _pi("linux", "centos", ("centos", "rhel"))
            )
        assert cmd[0] == "yum"
        assert "legacy" in reason.lower() or "yum" in reason


class TestBsdInstallerSelection:
    def test_freebsd_uses_pkg(self, find_setup):
        with patch("os.geteuid", return_value=0, create=True):
            cmd, _ = find_setup.select_installer(_pi("bsd", "freebsd"))
        assert cmd == ["pkg", "install", "-y", "fd-find"]

    def test_freebsd_sudo_when_not_root(self, find_setup):
        with patch("os.geteuid", return_value=1000, create=True):
            cmd, _ = find_setup.select_installer(_pi("bsd", "freebsd"))
        assert cmd[0] == "sudo"

    def test_openbsd_uses_pkg_add_with_doas(self, find_setup):
        with patch("os.geteuid", return_value=1000, create=True):
            cmd, reason = find_setup.select_installer(_pi("bsd", "openbsd"))
        # OpenBSD convention: doas, not sudo
        assert cmd[0] == "doas"
        assert "pkg_add" in cmd

    def test_unknown_bsd_returns_none(self, find_setup):
        cmd, reason = find_setup.select_installer(_pi("bsd", "netbsd"))
        assert cmd is None
        assert "netbsd" in reason


class TestIdempotency:
    def test_fd_already_installed_short_circuits(self, find_setup):
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda n: f"/usr/bin/{n}" if n == "fd" else None
            assert find_setup.fd_already_installed() == "/usr/bin/fd"

    def test_fdfind_on_debian_detected(self, find_setup):
        """Debian renames the binary to fdfind; idempotency check must catch that."""
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda n: (
                f"/usr/bin/{n}" if n == "fdfind" else None
            )
            assert find_setup.fd_already_installed() == "/usr/bin/fdfind"

    def test_neither_present_returns_none(self, find_setup):
        with patch("shutil.which", return_value=None):
            assert find_setup.fd_already_installed() is None


class TestDryRunFlag:
    """The --dry-run convention: print commands without executing."""

    def test_dry_run_does_not_invoke_subprocess(self, find_setup, capsys):
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            mock_which.side_effect = lambda n: (
                f"/fake/{n}.exe" if n in ("winget",) else None
            )
            # Ensure fd is NOT detected as already installed.
            mock_which.side_effect = lambda n: (
                f"/fake/{n}" if n == "winget" else None
            )
            with patch.object(find_setup, "get_platform_info",
                              return_value=_pi("windows", "win11")):
                rc = find_setup.main(["--dry-run", "--force"])
        assert rc == 0
        assert not mock_run.called  # subprocess.run NOT called in dry-run
        captured = capsys.readouterr()
        assert "winget install" in captured.out
        assert "--dry-run: not executing" in captured.out

    def test_already_installed_short_circuits_before_dry_run(self, find_setup, capsys):
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            mock_which.return_value = "/already/installed/fd"
            with patch.object(find_setup, "get_platform_info",
                              return_value=_pi("windows", "win11")):
                rc = find_setup.main([])
        assert rc == 0
        assert not mock_run.called
        captured = capsys.readouterr()
        assert "already installed" in captured.out
