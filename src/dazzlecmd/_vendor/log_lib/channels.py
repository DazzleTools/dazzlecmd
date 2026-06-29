"""
Channel configuration and parsing for the THAC0 verbosity system.

Channels are named output categories. Each channel can have its own
verbosity threshold (overriding the global level) and future properties
like destination, format, and location.

Channel spec syntax (compact, positional):
    CHANNEL:LEVEL:DEST:LOCATION:FORMAT

    Examples:
        timing              # All defaults (level=0)
        timing:2            # Level 2
        timing::file:perf.log   # Default level, file dest
        timing::stdout::json    # Default level, stdout, json

Expanded flags (like --iter-* pattern):
    --chan-lvl timing:2
    --chan-fmt timing:json
    --chan-dest timing:file
    --chan-file timing:perf.log
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, TextIO

from dazzle_lib.continuum import ContinuumSpace

from .verbosity import VERBOSITY_CONTINUUM, rank_of


# Channels currently used in the codebase
KNOWN_CHANNELS = {
    'config',       # Configuration loading and overrides
    'parse',        # Expression parsing
    'eval',         # Expression evaluation
    'iter',         # Iteration / search space
    'progress',     # Progress counters
    'timing',       # Timing information
    'algorithm',    # Algorithm selection
    'hint',         # Hint messages
    'error',        # Error messages
    'trace',        # Function tracing (@trace decorator)
    'vals',         # Computed LHS/RHS values on match output
    'general',      # Default channel
}

# Channel descriptions for --show listing
CHANNEL_DESCRIPTIONS = {
    'config':    'Configuration loading and overrides',
    'parse':     'Expression parsing details',
    'eval':      'Expression evaluation trace',
    'iter':      'Iteration / search space info',
    'progress':  'Progress counters during search',
    'timing':    'Timing and match count summary',
    'algorithm': 'Algorithm selection details',
    'hint':      'Contextual tips and suggestions',
    'error':     'Error messages',
    'trace':     'Function call tracing',
    'vals':      'Computed LHS/RHS values on matches',
    'general':   'General output',
}

# Channels that are OFF by default (require explicit --show to activate).
# These get a default override of -1, so channel_active() returns False
# unless the user explicitly enables them.
OPT_IN_CHANNELS = {
    'vals',     # Annotates stdout match lines — opt-in to avoid noise
    'trace',    # Function call tracing — opt-in (verbose debug output)
}

# DWP-B/B-2: the opt-in channels' cold starting rung, DECLARED via the verbosity
# Continuum (was a baked-in -1 in init_output). They start at `minimal` (-1) so a
# level-0 message is suppressed until `--show <chan>` raises the channel.
OPT_IN_START_RANK = rank_of("minimal")  # -1


def default_channel_overrides() -> Dict[str, int]:
    """The per-channel starting coordinates: opt-in channels begin cold (`minimal`);
    every other channel defers to the global verbosity (no override)."""
    return {ch: OPT_IN_START_RANK for ch in OPT_IN_CHANNELS}


# DWP-B/B-2: channels x verbosity as a ContinuumSpace -- each KNOWN channel is an
# axis carrying the SAME verbosity Continuum (continuum.py's "channels are the
# orthogonal sub-dimension"). A running OutputManager's (global verbosity +
# channel_overrides) is a COORDINATE in this space; a per-channel `--show` moves
# one axis. Structural model; the emit gate reads a single channel's rung via
# `shows()`.
VERBOSITY_SPACE = ContinuumSpace.compose(
    "verbosity_space",
    {ch: VERBOSITY_CONTINUUM for ch in sorted(KNOWN_CHANNELS)},
    meaning="per-channel verbosity: each output channel's loudness, independently",
)


@dataclass
class ChannelConfig:
    """Configuration for a single output channel.

    Attributes:
        name: Channel identifier
        level: Default verbosity level override (0 = global default)
        fd: Default output file handle for this channel (None = use manager default)
        destination: Future (DazzleLib) — 'stderr', 'stdout', 'file', 'fdN'
        location: Future (DazzleLib) — File path for file dest
        format: Future (DazzleLib) — 'text', 'json', 'csv'
    """
    name: str
    level: int = 0
    fd: Optional[TextIO] = None          # Channel's default output FD
    # Stubs for future use — stored but not routed yet
    destination: Optional[str] = None    # 'stderr', 'stdout', 'file', 'fdN'
    location: Optional[str] = None       # File path for file dest
    format: Optional[str] = None         # 'text', 'json', 'csv'


def _resolve_level(token: str) -> int:
    """A channel spec's level slot: a raw int (`'2'`) OR a NAMED verbosity rung
    (`'config'` -> 2) resolved via the verbosity Continuum (DWP-B/B-2). The named
    form is the continuum reaching the `--show timing:config` surface."""
    try:
        return int(token)
    except ValueError:
        return rank_of(token)


def parse_channel_spec(spec: str) -> ChannelConfig:
    """Parse a channel spec string into a ChannelConfig.

    Handles the compact positional syntax:
        CHANNEL:LEVEL:DEST:LOCATION:FORMAT

    Empty slots use :: (empty between colons).
    Windows drive letters (e.g., C:\\path) are detected and rejoined.

    Args:
        spec: Channel spec string like "timing:2" or "timing::file:C:\\logs\\out.log"

    Returns:
        ChannelConfig with parsed values
    """
    parts = spec.split(':')

    # Handle Windows drive letters: rejoin 'C' + 'path' into 'C:path'
    # A single alpha character followed by another part is likely a drive letter
    rejoined = []
    i = 0
    while i < len(parts):
        if (len(parts[i]) == 1 and parts[i].isalpha()
                and i + 1 < len(parts)
                and i >= 3):  # Only in LOCATION slot (position 3+)
            rejoined.append(f"{parts[i]}:{parts[i+1]}")
            i += 2
        else:
            rejoined.append(parts[i])
            i += 1
    parts = rejoined

    name = parts[0] if len(parts) > 0 else ''
    level = 0
    dest = location = fmt = None

    if len(parts) > 1 and parts[1]:
        level = _resolve_level(parts[1])   # int OR named rung ('config')
    if len(parts) > 2 and parts[2]:
        dest = parts[2]
    if len(parts) > 3 and parts[3]:
        location = parts[3]
    if len(parts) > 4 and parts[4]:
        fmt = parts[4]

    return ChannelConfig(name=name, level=level, destination=dest,
                         location=location, format=fmt)


def format_channel_list() -> str:
    """Format the list of known channels for display.

    Returns:
        Formatted string listing all channels with descriptions.
    """
    lines = ["Available channels:"]
    max_name = max(len(name) for name in KNOWN_CHANNELS)
    for name in sorted(KNOWN_CHANNELS):
        desc = CHANNEL_DESCRIPTIONS.get(name, '')
        lines.append(f"  {name:<{max_name}}  {desc}")
    return "\n".join(lines)
