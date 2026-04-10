#!/usr/bin/env python3
"""Run safedel test suite.

Usage:
    python run_tests.py              # run all tests
    python run_tests.py -v           # verbose
    python run_tests.py -k zones     # filter by name
    python run_tests.py --tb=short   # short tracebacks
"""

import subprocess
import sys
import os

def main():
    test_dir = os.path.join(os.path.dirname(__file__), "tests")
    # Use sys.executable so we run with the same Python interpreter
    # (handles python3 on Unix, python on Windows, virtualenvs, etc.)
    args = [sys.executable, "-m", "pytest", test_dir, "--tb=short"] + sys.argv[1:]
    return subprocess.call(args, cwd=os.path.dirname(__file__))

if __name__ == "__main__":
    sys.exit(main())
