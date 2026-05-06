"""Debug script for fixpath directory search chain."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'projects', 'core', 'fixpath'))
import fixpath

pattern = "Taleb, Nassim/"
dir_only = pattern.rstrip(" ").endswith("/") or pattern.rstrip(" ").endswith("\\")
print(f"dir_only: {dir_only}")

search_pattern, search_roots = fixpath._resolve_search_context(pattern, None, {})
print(f"search_pattern: {search_pattern!r}")
print(f"search_roots: {search_roots}")

# Test Everything directly
results = fixpath._run_everything_search(search_pattern, search_roots, dir_only=dir_only)
print(f"Everything results: {results}")

# Test fd directly
results = fixpath._run_fd_search(search_pattern, search_roots, dir_only=dir_only)
print(f"fd results: {results}")
