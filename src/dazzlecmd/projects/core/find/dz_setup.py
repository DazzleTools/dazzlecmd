"""Setup script for `dz find` -- installs the fd binary on any major platform.

Real-world validator for v0.7.46's setup-script API. Consumes
``dazzlecmd_lib.platform_detect`` (the lib's shared identity primitive)
to identify the host OS / distro family, then dispatches the right
installer command. The engine never makes installer decisions -- this
script does, on a per-tool basis. dazzlecmd-lib gives us the facts;
the policy lives here.

Convention: this script honors ``--dry-run`` (print what would run, do
not execute). All `dazzlecmd-pattern` setup scripts SHOULD support
``--dry-run`` so users can preview destructive or elevated operations
before committing. The convention is policy, not code -- the engine
does not enforce it.

Idempotency: the script short-circuits with "already installed" when
``fd`` or ``fdfind`` is already on PATH. Re-running ``dz setup find``
on an already-set-up machine is a no-op.

Platform coverage:
    - Windows (winget > scoop > choco precedence; first one on PATH wins)
    - macOS (brew)
    - Linux (per-distro: apt-get / dnf / pacman / apk; uses pi.id_like
      so debian-derived distros all get apt-get, rhel-derived all get
      dnf, arch-derived all get pacman, alpine gets apk)
    - FreeBSD (pkg install fd-find)
    - OpenBSD (pkg_add fd)

Linux + BSD installers need root; the script prepends ``sudo`` when not
already root and prints the full command before running so users see
the elevation prompt.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

from dazzlecmd_lib.platform_detect import PlatformInfo, get_platform_info


# Binary names to check for -- fd is the upstream name; fdfind is the
# Debian/Ubuntu rename (binary conflict with another package).
FD_BINARY_NAMES = ("fd", "fdfind")


def fd_already_installed() -> Optional[str]:
    """Return the path to fd (or fdfind on Debian/Ubuntu) if already on PATH."""
    for name in FD_BINARY_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None


def _which_first(candidates) -> Optional[str]:
    """Return the first PATH-resolvable name from ``candidates`` or None."""
    for name in candidates:
        if shutil.which(name):
            return name
    return None


def _needs_sudo() -> bool:
    """True when running as a non-root user on a POSIX system."""
    if not hasattr(os, "geteuid"):
        return False
    return os.geteuid() != 0


def select_installer(pi: PlatformInfo) -> Tuple[Optional[List[str]], str]:
    """Pick the install command for the given platform.

    Returns a (command, reason) tuple. command is the argv list to run,
    or None when no supported installer applies on this host. reason is
    a one-line description that goes into stdout / the --dry-run output.
    """
    # Windows: try winget, scoop, choco in that precedence order. First
    # one on PATH wins. winget is now bundled with modern Windows; scoop
    # and choco are popular community alternatives.
    if pi.os == "windows":
        tool = _which_first(["winget", "scoop", "choco"])
        if tool == "winget":
            return (
                ["winget", "install", "--id", "sharkdp.fd", "-e",
                 "--accept-source-agreements", "--accept-package-agreements"],
                "winget (sharkdp.fd)",
            )
        if tool == "scoop":
            return (["scoop", "install", "fd"], "scoop (fd)")
        if tool == "choco":
            return (["choco", "install", "-y", "fd"], "choco (fd)")
        return (
            None,
            "Windows: none of winget / scoop / choco found on PATH. "
            "Install one of them, or download fd from "
            "https://github.com/sharkdp/fd/releases",
        )

    # macOS: brew is the standard. MacPorts users can install manually.
    if pi.os == "macos":
        if shutil.which("brew"):
            return (["brew", "install", "fd"], "brew (fd)")
        return (
            None,
            "macOS: Homebrew not found on PATH. Install from https://brew.sh "
            "or run `port install fd` if you use MacPorts.",
        )

    # Linux: two-tier dispatch.
    #
    # Tier 1 (semantic): pi.id_like maps distros to families. id_like
    # includes the subtype itself first so direct-ID matches also resolve
    # here. Tier 1 gets the correct binary name AND distro-appropriate
    # flags (e.g. fd-find vs fd; --noconfirm vs -y).
    #
    # Tier 2 (binary detection): when id_like doesn't match (Gentoo / Void
    # / NixOS / distro that fails to declare ID_LIKE properly), fall back
    # to detecting whichever package manager is on PATH. The fallback
    # picks sensible defaults but can't promise binary-name accuracy --
    # if a distro renames fd to fdfind without declaring debian-family,
    # the post-install verification will catch it.
    if pi.os == "linux":
        cmd: Optional[List[str]] = None
        why = ""

        # --- Tier 1: distro family via id_like ---
        if "debian" in pi.id_like or "ubuntu" in pi.id_like:
            cmd = ["apt-get", "install", "-y", "fd-find"]
            why = f"apt-get (fd-find -- binary installs as 'fdfind' on {pi.subtype})"
        elif "rhel" in pi.id_like or "fedora" in pi.id_like or "centos" in pi.id_like:
            # dnf preferred; fall back to yum on older RHEL/CentOS 7
            if shutil.which("dnf"):
                cmd = ["dnf", "install", "-y", "fd-find"]
                why = "dnf (fd-find)"
            elif shutil.which("yum"):
                cmd = ["yum", "install", "-y", "fd-find"]
                why = "yum (fd-find -- legacy RHEL/CentOS)"
        elif "arch" in pi.id_like:
            cmd = ["pacman", "-S", "--noconfirm", "fd"]
            why = "pacman (fd)"
        elif "alpine" in pi.id_like:
            cmd = ["apk", "add", "fd"]
            why = "apk (fd)"
        elif "suse" in pi.id_like:
            cmd = ["zypper", "install", "-y", "fd"]
            why = "zypper (fd)"
        elif "gentoo" in pi.id_like:
            cmd = ["emerge", "--ask=n", "sys-apps/fd"]
            why = "emerge (sys-apps/fd)"
        elif "solus" in pi.id_like:
            cmd = ["eopkg", "install", "-y", "fd"]
            why = "eopkg (fd)"

        # --- Tier 2: package-manager-binary detection fallback ---
        # Runs only when Tier 1 found no match. Precedence reflects
        # "what would a sysadmin reach for first on an unknown box".
        if cmd is None:
            pm_fallbacks = [
                (["apt-get", "install", "-y", "fd-find"],
                 "apt-get (binary-detect fallback; tool may install as 'fdfind')",
                 "apt-get"),
                (["dnf", "install", "-y", "fd-find"],
                 "dnf (binary-detect fallback)", "dnf"),
                (["yum", "install", "-y", "fd-find"],
                 "yum (binary-detect fallback)", "yum"),
                (["pacman", "-S", "--noconfirm", "fd"],
                 "pacman (binary-detect fallback)", "pacman"),
                (["apk", "add", "fd"],
                 "apk (binary-detect fallback)", "apk"),
                (["zypper", "install", "-y", "fd"],
                 "zypper (binary-detect fallback)", "zypper"),
                (["xbps-install", "-S", "-y", "fd"],
                 "xbps-install (binary-detect fallback; Void)", "xbps-install"),
                (["emerge", "--ask=n", "sys-apps/fd"],
                 "emerge (binary-detect fallback; Gentoo)", "emerge"),
                (["nix-env", "-iA", "nixpkgs.fd"],
                 "nix-env (binary-detect fallback; NixOS)", "nix-env"),
                (["eopkg", "install", "-y", "fd"],
                 "eopkg (binary-detect fallback; Solus)", "eopkg"),
            ]
            for fallback_cmd, fallback_why, pm_name in pm_fallbacks:
                if shutil.which(pm_name):
                    cmd = fallback_cmd
                    why = fallback_why
                    break

        if cmd is None:
            return (
                None,
                f"Linux distro {pi.subtype!r} (id_like={pi.id_like!r}) is not "
                f"in the built-in installer matrix and no recognized package "
                f"manager was found on PATH. Install fd manually from "
                f"https://github.com/sharkdp/fd#installation",
            )

        if _needs_sudo():
            cmd = ["sudo"] + cmd
            why = "sudo " + why
        return cmd, why

    # BSD family
    if pi.os == "bsd":
        if pi.subtype == "freebsd":
            cmd = ["pkg", "install", "-y", "fd-find"]
            why = "pkg install fd-find (FreeBSD)"
            if _needs_sudo():
                cmd = ["sudo"] + cmd
                why = "sudo " + why
            return cmd, why
        if pi.subtype == "openbsd":
            cmd = ["pkg_add", "fd"]
            why = "pkg_add fd (OpenBSD)"
            if _needs_sudo():
                cmd = ["doas"] + cmd  # OpenBSD convention
                why = "doas " + why
            return cmd, why
        return (
            None,
            f"BSD variant {pi.subtype!r} is not in the installer matrix. "
            f"Install fd from https://github.com/sharkdp/fd#installation",
        )

    return (
        None,
        f"Platform {pi.os!r} subtype={pi.subtype!r} is not recognized. "
        f"Install fd manually from https://github.com/sharkdp/fd#installation",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="dz setup find",
        description="Install fd, the file-search binary that `dz find` wraps.",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Print the chosen installer command without running it.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run the installer even if fd is already on PATH (default: skip).",
    )
    args = parser.parse_args(argv)

    pi = get_platform_info()
    print(
        f"[dz setup find] host: os={pi.os} subtype={pi.subtype} "
        f"arch={pi.arch} wsl={pi.is_wsl}"
        + (f" id_like={pi.id_like}" if pi.id_like else "")
    )

    existing = fd_already_installed()
    if existing and not args.force:
        print(f"[dz setup find] fd is already installed at: {existing}")
        print("[dz setup find] Nothing to do. Use --force to reinstall anyway.")
        return 0

    cmd, reason = select_installer(pi)
    print(f"[dz setup find] installer: {reason}")
    if cmd is None:
        # No supported installer on this host. select_installer's reason
        # already explains; the manual link is in there too.
        return 1

    print(f"$ {' '.join(cmd)}")
    if args.dry_run:
        print("[dz setup find] --dry-run: not executing.")
        return 0

    try:
        result = subprocess.run(cmd)
    except FileNotFoundError as exc:
        # The chosen installer disappeared between detection and dispatch
        # (unlikely but possible if PATH changes mid-run).
        print(f"Error: installer not on PATH at dispatch time: {exc}",
              file=sys.stderr)
        return 1

    if result.returncode != 0:
        print(
            f"[dz setup find] installer exited {result.returncode}. "
            f"fd may not be installed; check the output above.",
            file=sys.stderr,
        )
        return result.returncode

    # Post-install verification -- the dispatcher-not-package-manager
    # promise means we can't trust the installer's exit code alone.
    installed_at = fd_already_installed()
    if installed_at:
        print(f"[dz setup find] success. fd available at: {installed_at}")
        return 0
    print(
        "[dz setup find] installer reported success but fd is not on PATH.\n"
        "                You may need to open a new shell, or add the install "
        "directory to PATH.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
