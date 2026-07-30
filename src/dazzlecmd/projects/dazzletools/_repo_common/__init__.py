"""Shared git-repo inspection primitives for dazzletools tools.

Consumed by `dz git` (single-repo CLI) and `dz dazzle-update`
(multi-repo scanner). Every function here is location-explicit: it
takes the repo path as an argument and never depends on, or mutates,
the process working directory. Repo discovery, interactive prompts,
and output layout are CLI concerns and live in the consuming tool.

This directory has no .dazzlecmd.json manifest, which is what keeps it
out of tool discovery -- the leading underscore is a human signal only.
"""
