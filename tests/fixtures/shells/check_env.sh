#!/bin/sh
if [ "$FROM_ENV" = "yes" ]; then
    echo "ENV_OK marker=$DZ_TEST_MARKER"
else
    echo "ENV_MISSING"
fi
