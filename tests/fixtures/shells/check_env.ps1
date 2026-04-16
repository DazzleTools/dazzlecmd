if ($env:FROM_ENV -eq "yes") {
    Write-Host "ENV_OK marker=$($env:DZ_TEST_MARKER)"
} else {
    Write-Host "ENV_MISSING"
}
