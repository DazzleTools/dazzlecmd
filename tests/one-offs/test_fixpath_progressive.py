"""Debug progressive resolve for the Taleb scenario from D:\M."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'projects', 'core', 'fixpath'))

os.chdir("D:\\M")
print(f"CWD: {os.getcwd()}")

import fixpath

pattern = "Literature/Books/__Politics, Social Science, and Intelligence/__Economics/__Famous Economists and Writings/Taleb, Nassim/"
pattern_clean = pattern.rstrip("/\\")
print(f"pattern_clean: {pattern_clean}")

resolved_dir, remainder = fixpath._progressive_resolve(pattern_clean)
print(f"resolved_dir: {resolved_dir}")
print(f"remainder: {remainder}")

basename = os.path.basename(remainder.rstrip("/\\")) if remainder else ""
print(f"search basename: {basename!r}")

# Now test the actual search
from fixpath import _run_fd_search
results = _run_fd_search(basename, [resolved_dir] if resolved_dir else ["."], dir_only=True)
print(f"fd results: {results}")
