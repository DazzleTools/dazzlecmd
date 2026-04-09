"""Pytest configuration for safedel tests.

Sets up sys.path so safedel modules and their dependencies are importable.
"""

import os
import sys

# Add safedel root to path
_safedel_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _safedel_dir)

# Add _lib for preservelib, log_lib, etc.
sys.path.insert(0, os.path.join(_safedel_dir, "_lib"))

# Add sibling links tool for detect_link imports
sys.path.insert(0, os.path.join(_safedel_dir, "..", "links"))
