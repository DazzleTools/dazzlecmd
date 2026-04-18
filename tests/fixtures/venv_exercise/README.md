# venv-exercise -- synthetic stress-test fixture

A synthetic tool used by the v0.7.20 integration test suite to validate the
full venv-per-tool flow:

1. `dz setup venv-exercise` creates `.venv/` and installs heavy dependencies
   (numpy, pandas, requests, rich, pyyaml, click, pydantic).
2. `dz venv-exercise` dispatches via the venv's Python interpreter, NOT the
   calling process's `sys.executable`.
3. The tool script imports every declared dependency and exercises a small
   operation on each. Any import failure surfaces in the machine-parsable
   report on stdout.

## Running the integration test

```
pytest tests/test_venv_integration.py -m venv_integration
```

The test is opt-in via the `venv_integration` marker because pip install
across ~7 packages (~50-150MB of wheels) takes 30-120 seconds depending on
network speed. Not suitable for fast CI cycles.

## Why this fixture exists

Zero in-repo tools currently require venv isolation -- all dazzletools run
in ambient Python. This fixture validates the venv pattern end-to-end so
real tools that need venvs (ML tools wanting specific pandas/torch versions,
Windows tools pinning pywin32, etc.) can adopt the pattern with confidence.

See the v0.7.20 CHANGELOG entry and the parent v0.7.19 postmortem's "why
4b.3 slipped" analysis for the full context.
