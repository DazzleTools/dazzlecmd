@echo off
if "%FROM_ENV%"=="yes" (
    echo ENV_OK marker=%DZ_TEST_MARKER%
) else (
    echo ENV_MISSING
)
