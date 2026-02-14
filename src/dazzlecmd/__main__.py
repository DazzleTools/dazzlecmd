"""Allow running as: python -m dazzlecmd"""

import sys

from dazzlecmd.cli import main

if __name__ == "__main__":
    sys.exit(main())
