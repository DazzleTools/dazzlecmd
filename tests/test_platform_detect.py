"""Tests for dazzlecmd_lib.platform_detect."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch, mock_open

import pytest

from dazzlecmd_lib.platform_detect import (
    PlatformInfo,
    _detect_wsl,
    _normalize_arch,
    _detect_linux_subtype,
    _detect_windows_subtype,
    _detect_macos_subtype,
    _detect_bsd_subtype,
    _detect_platform_info_uncached,
    get_platform_info,
)


class TestPlatformInfoDataclass:
    def test_construction_with_all_fields(self):
        info = PlatformInfo(
            os="linux",
            subtype="debian",
            arch="x86_64",
            is_wsl=False,
            version="12",
            raw={"distro_id": "debian"},
        )
        assert info.os == "linux"
        assert info.subtype == "debian"
        assert info.arch == "x86_64"
        assert info.is_wsl is False
        assert info.version == "12"
        assert info.raw == {"distro_id": "debian"}

    def test_frozen(self):
        info = PlatformInfo(
            os="linux", subtype=None, arch="x86_64", is_wsl=False, version=None
        )
        with pytest.raises((AttributeError, Exception)):
            info.os = "windows"  # type: ignore

    def test_raw_excluded_from_equality(self):
        a = PlatformInfo(
            os="linux", subtype="debian", arch="x86_64", is_wsl=False, version="12",
            raw={"a": 1},
        )
        b = PlatformInfo(
            os="linux", subtype="debian", arch="x86_64", is_wsl=False, version="12",
            raw={"b": 2},
        )
        assert a == b


class TestNormalizeArch:
    @pytest.mark.parametrize("input,expected", [
        ("x86_64", "x86_64"),
        ("AMD64", "x86_64"),
        ("amd64", "x86_64"),
        ("aarch64", "arm64"),
        ("ARM64", "arm64"),
        ("i386", "i386"),
        ("i686", "i386"),
        ("x86", "i386"),
        ("", "unknown"),
        ("riscv64", "riscv64"),
    ])
    def test_normalization(self, input, expected):
        assert _normalize_arch(input) == expected


class TestDetectWsl:
    def test_env_var_set(self, monkeypatch):
        monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-22.04")
        assert _detect_wsl() is True

    def test_proc_version_contains_microsoft(self, monkeypatch):
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        m = mock_open(read_data="Linux version 5.15.0-microsoft-standard-WSL2")
        with patch("builtins.open", m):
            assert _detect_wsl() is True

    def test_proc_version_native_linux(self, monkeypatch):
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        m = mock_open(read_data="Linux version 6.1.0-12-amd64 gcc 12.2.0")
        with patch("builtins.open", m):
            assert _detect_wsl() is False

    def test_no_proc_version(self, monkeypatch):
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        with patch("builtins.open", side_effect=OSError):
            assert _detect_wsl() is False


class TestDetectLinuxSubtype:
    def test_distro_package_available(self, monkeypatch):
        fake_distro = type("distro", (), {})()
        fake_distro.id = lambda: "debian"
        fake_distro.version = lambda: "12"
        fake_distro.name = lambda: "Debian GNU/Linux"
        monkeypatch.setitem(sys.modules, "distro", fake_distro)
        subtype, version, raw = _detect_linux_subtype()
        assert subtype == "debian"
        assert version == "12"
        assert raw["distro_id"] == "debian"

    def test_os_release_fallback(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "distro", None)
        os_release = (
            'NAME="Ubuntu"\n'
            'VERSION_ID="22.04"\n'
            'ID=ubuntu\n'
            'PRETTY_NAME="Ubuntu 22.04.3 LTS"\n'
        )
        with patch("builtins.open", mock_open(read_data=os_release)):
            subtype, version, raw = _detect_linux_subtype()
        assert subtype == "ubuntu"
        assert version == "22.04"

    def test_no_detection_possible(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "distro", None)
        with patch("builtins.open", side_effect=OSError):
            subtype, version, raw = _detect_linux_subtype()
        assert subtype is None
        assert version is None


class TestDetectWindowsSubtype:
    def test_win11_by_build_number(self, monkeypatch):
        monkeypatch.setattr("platform.release", lambda: "10")
        monkeypatch.setattr("platform.version", lambda: "10.0.22621")
        subtype, version, raw = _detect_windows_subtype()
        assert subtype == "win11"
        assert version == "10.0.22621"

    def test_win10_by_build_number(self, monkeypatch):
        monkeypatch.setattr("platform.release", lambda: "10")
        monkeypatch.setattr("platform.version", lambda: "10.0.19045")
        subtype, version, raw = _detect_windows_subtype()
        assert subtype == "win10"

    def test_win11_by_release_string(self, monkeypatch):
        monkeypatch.setattr("platform.release", lambda: "11")
        monkeypatch.setattr("platform.version", lambda: "")
        subtype, version, raw = _detect_windows_subtype()
        assert subtype == "win11"

    def test_unknown_version(self, monkeypatch):
        monkeypatch.setattr("platform.release", lambda: "7")
        monkeypatch.setattr("platform.version", lambda: "6.1.7601")
        subtype, version, raw = _detect_windows_subtype()
        assert subtype is None


class TestDetectMacosSubtype:
    def test_macos_version(self, monkeypatch):
        monkeypatch.setattr("platform.mac_ver", lambda: ("14.2.1", ("", "", ""), ""))
        subtype, version, raw = _detect_macos_subtype()
        assert subtype == "macos14"
        assert version == "14.2.1"

    def test_no_mac_ver(self, monkeypatch):
        monkeypatch.setattr("platform.mac_ver", lambda: ("", ("", "", ""), ""))
        subtype, version, raw = _detect_macos_subtype()
        assert subtype is None


class TestDetectBsdSubtype:
    @pytest.mark.parametrize("system,expected", [
        ("FreeBSD", "freebsd"),
        ("freebsd", "freebsd"),
        ("OpenBSD", "openbsd"),
        ("NetBSD", "netbsd"),
        ("DragonFly", "dragonfly"),
        ("UnknownBSD", None),
    ])
    def test_variants(self, system, expected):
        subtype, version, raw = _detect_bsd_subtype(system)
        assert subtype == expected


class TestDetectPlatformInfoUncached:
    def test_linux_detection(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("platform.machine", lambda: "x86_64")
        monkeypatch.setattr("platform.release", lambda: "6.1.0")
        monkeypatch.setenv("WSL_DISTRO_NAME", "")
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        monkeypatch.setitem(sys.modules, "distro", None)
        with patch("builtins.open", side_effect=OSError):
            info = _detect_platform_info_uncached()
        assert info.os == "linux"
        assert info.arch == "x86_64"
        assert info.subtype is None

    def test_windows_detection(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Windows")
        monkeypatch.setattr("platform.machine", lambda: "AMD64")
        monkeypatch.setattr("platform.release", lambda: "10")
        monkeypatch.setattr("platform.version", lambda: "10.0.22621")
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        with patch("builtins.open", side_effect=OSError):
            info = _detect_platform_info_uncached()
        assert info.os == "windows"
        assert info.subtype == "win11"
        assert info.arch == "x86_64"

    def test_macos_detection(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")
        monkeypatch.setattr("platform.release", lambda: "23.2.0")
        monkeypatch.setattr("platform.mac_ver", lambda: ("14.2.1", ("", "", ""), ""))
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        with patch("builtins.open", side_effect=OSError):
            info = _detect_platform_info_uncached()
        assert info.os == "macos"
        assert info.subtype == "macos14"
        assert info.arch == "arm64"

    def test_freebsd_detection(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "FreeBSD")
        monkeypatch.setattr("platform.machine", lambda: "amd64")
        monkeypatch.setattr("platform.release", lambda: "13.2-RELEASE")
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        with patch("builtins.open", side_effect=OSError):
            info = _detect_platform_info_uncached()
        assert info.os == "bsd"
        assert info.subtype == "freebsd"
        assert info.arch == "x86_64"

    def test_unknown_os(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Haiku")
        monkeypatch.setattr("platform.machine", lambda: "x86_64")
        monkeypatch.setattr("platform.release", lambda: "R1")
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        with patch("builtins.open", side_effect=OSError):
            info = _detect_platform_info_uncached()
        assert info.os == "other"
        assert info.subtype is None

    def test_wsl_detected_as_linux(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("platform.machine", lambda: "x86_64")
        monkeypatch.setattr("platform.release", lambda: "5.15.0")
        monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-22.04")
        monkeypatch.setitem(sys.modules, "distro", None)
        with patch("builtins.open", side_effect=OSError):
            info = _detect_platform_info_uncached()
        assert info.os == "linux"
        assert info.is_wsl is True

    def test_subtype_lowercased(self, monkeypatch):
        fake_distro = type("distro", (), {})()
        fake_distro.id = lambda: "Debian"  # uppercase from upstream
        fake_distro.version = lambda: "12"
        fake_distro.name = lambda: "Debian"
        monkeypatch.setitem(sys.modules, "distro", fake_distro)
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("platform.machine", lambda: "x86_64")
        monkeypatch.setattr("platform.release", lambda: "6.1.0")
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        info = _detect_platform_info_uncached()
        assert info.subtype == "debian"


class TestGetPlatformInfoCaching:
    def test_same_instance_returned(self):
        get_platform_info.cache_clear()
        a = get_platform_info()
        b = get_platform_info()
        assert a is b

    def test_cache_clear_works(self):
        get_platform_info.cache_clear()
        a = get_platform_info()
        get_platform_info.cache_clear()
        b = get_platform_info()
        # Same value but not necessarily the same instance after clear
        assert a == b
