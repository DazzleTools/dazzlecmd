# docker-test-tool -- synthetic Docker integration fixture

Real Docker-based fixture for the v0.7.21 integration test suite. Exercises
the end-to-end flow:

1. `dz setup` builds an image (`docker build -t dazzlecmd-test-docker-tool:v1 .`)
2. `dz docker-test-tool [args]` runs that image via the Docker runner
3. The container emits a machine-parsable report (`DAZZLECMD_DOCKER_TEST_*`)
4. The integration test asserts on the report

Base image: `python:3.11-alpine` (~50MB). The container runs as a non-root
user (`dztest`) and exposes an ENTRYPOINT that prints a structured report.

## What the integration test validates

- Image build via manifest `setup.command` with `_vars` substitution
- `dz info --raw` and default views render Docker fields correctly
- `docker images -q` pre-flight check passes when image present, fails cleanly on miss
- `docker run` argv construction matches manifest declaration
- `env_passthrough` passes host env vars without leaking values to argv
- `env` dict sets explicit container env vars
- `docker_args` flags reach `docker run` in the right position
- Volume mounts work (when the test passes `-v`)
- `inner_runtime` field is informational only -- does NOT influence dispatch
- Exit code propagates from container to dz

## Running the integration tests

```
pytest tests/test_docker_integration.py -v -m docker_integration
```

Opt-in via the `docker_integration` pytest marker. Auto-skipped when `docker`
command is absent (see `tests/conftest.py`). First run builds the image
(~30-90s cold); subsequent runs reuse the image for speed.

## Cleanup

To remove the fixture image after testing:

```
docker rmi dazzlecmd-test-docker-tool:v1
```

The test suite does NOT auto-remove the image -- keeping it cached speeds up
subsequent runs.

## Why this exists

Mocked unit tests (in `tests/test_docker_runner.py`) prove argv construction
and error paths are correct. They do NOT prove the full flow actually works
against a real Docker daemon. This fixture fills that gap: build + run + exit
code + output capture against the real thing.

Parallels `tests/fixtures/venv_exercise/` (v0.7.20) which did the same for the
venv-per-tool pattern.
