#!/usr/bin/env python3
"""Fixture tool: prints structured report for the v0.7.21 Docker integration test.

Emits a machine-parsable report that lets the test assert:
    - the signature proves this is OUR container, not a collision
    - ARGV count + individual args prove argv propagation
    - env vars prove env_passthrough and env dict work
    - volume mount content proves -v mounts work
    - container hostname differs from host (proves isolation)
"""

from __future__ import annotations

import os
import platform
import sys


def main() -> int:
    print("DAZZLECMD_DOCKER_TEST_SIGNATURE=v1")
    print(f"DAZZLECMD_DOCKER_TEST_HOSTNAME={platform.node()}")
    print(f"DAZZLECMD_DOCKER_TEST_UNAME_SYSTEM={platform.system()}")
    print(f"DAZZLECMD_DOCKER_TEST_PYTHON_VERSION={sys.version.split()[0]}")

    # Env var report (read a known set of names; never log host secrets)
    watched = [
        "DAZZLECMD_DOCKER_TEST_ENV1",
        "DAZZLECMD_DOCKER_TEST_ENV2",
        "DAZZLECMD_DOCKER_TEST_EXPLICIT_ENV",
        "HOME",
        "PATH",  # always present in container
    ]
    for name in watched:
        value = os.environ.get(name, "<unset>")
        # Truncate to 200 chars to avoid flooding output if PATH is huge
        if len(value) > 200:
            value = value[:197] + "..."
        print(f"DAZZLECMD_DOCKER_TEST_ENV:{name}={value}")

    # Argv report
    argv = sys.argv[1:]
    print(f"DAZZLECMD_DOCKER_TEST_ARGV_COUNT={len(argv)}")
    for i, arg in enumerate(argv):
        print(f"DAZZLECMD_DOCKER_TEST_ARGV[{i}]={arg}")

    # Volume mount probe
    mount_marker = "/work/mount_marker.txt"
    if os.path.exists(mount_marker):
        with open(mount_marker, "r", encoding="utf-8") as f:
            content = f.read().strip()
        print(f"DAZZLECMD_DOCKER_TEST_VOLUME_CONTENT={content}")
    else:
        print("DAZZLECMD_DOCKER_TEST_VOLUME_CONTENT=<not mounted>")

    return 0


if __name__ == "__main__":
    sys.exit(main())
