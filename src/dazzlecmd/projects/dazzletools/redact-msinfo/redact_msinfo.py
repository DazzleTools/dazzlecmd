"""
redact-msinfo -- redact a Windows msinfo32 text export for safe sharing.

Takes a System Information (msinfo32) ".txt" export -- which is UTF-16 LE and
packed with hardware identifiers, serial numbers, network addresses, user
names, and a near-total inventory of installed software -- and produces a
UTF-8, ASCII-safe redaction suitable for coordinated disclosure, bug reports,
or any context where you want to share OS/hardware identity without leaking
PII or your full software footprint.

Two layers of redaction:
  1. Section selection.  A small default set of sections is kept verbatim
     ([System Summary], [Display], [Problem Devices]); every other section is
     replaced with a one-line placeholder noting why it was removed.  Use
     --include / --exclude to override the defaults per run.
  2. PII scrubbing.  Within kept sections, hostnames, user names, product
     keys, UUIDs, serial numbers, MAC addresses, IP addresses, and user
     profile paths are replaced with [REDACTED-*] tokens.

After writing, a self-verification pass confirms the obvious identifiers
(hostname, MAC, IP, volume serials, user name) are actually gone.

Input : UTF-16 LE (the format msinfo32 "Save"/"Export" produces).
Output: UTF-8, ASCII-only (safe on Windows codepage 437/1252 terminals).

Usage:
    dz redact-msinfo --input msinfo.txt
    dz redact-msinfo --input msinfo.txt --output clean.txt
    dz redact-msinfo --input msinfo.txt --include "System Drivers,Environment Variables"
    dz redact-msinfo --input msinfo.txt --exclude Display,ProblemDevices
    dz redact-msinfo --input msinfo.txt --include SystemDrivers --exclude Services
    dz redact-msinfo --list-sections          # show every known section + default disposition
    dz redact-msinfo --input msinfo.txt --no-verify

Section names for --include / --exclude are matched loosely: case, spaces, and
surrounding brackets are ignored, so "System Drivers", "system drivers",
"SystemDrivers", and "[System Drivers]" all refer to the same section.
"""

import re
import os
import sys
import socket
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIG -- section dispositions and PII rules
# ---------------------------------------------------------------------------

# Sections kept verbatim by default (the header line is always emitted).
# Matched against the bracketed header text exactly as it appears in the file,
# e.g. "[Display]" matches the line that reads "[Display]".
KEEP_SECTIONS = {
    "[System Summary]",
    "[Display]",
    "[Problem Devices]",
}

# Sections stripped by default.  Every section not in KEEP_SECTIONS is
# stripped regardless; listing known sections here lets us emit a
# purpose-tailored placeholder comment for each.
STRIP_REASONS = {
    "[Hardware Resources]":   "low-level hardware maps (IRQ/DMA/memory) -- rarely relevant",
    "[Conflicts/Sharing]":    "IRQ/DMA conflict table -- rarely relevant",
    "[DMA]":                  "DMA resource table -- rarely relevant",
    "[Forced Hardware]":      "forced hardware table -- rarely relevant",
    "[I/O]":                  "I/O port map -- rarely relevant",
    "[IRQs]":                 "IRQ table -- rarely relevant",
    "[Memory]":               "memory map -- rarely relevant",
    "[Multimedia]":           "multimedia codecs -- rarely relevant",
    "[Audio Codecs]":         "audio codec list -- rarely relevant",
    "[Video Codecs]":         "video codec list -- rarely relevant",
    "[CD-ROM]":               "optical drive table -- rarely relevant",
    "[Sound Device]":         "audio device table -- rarely relevant",
    "[Infrared]":             "infrared device table -- rarely relevant",
    "[Input]":                "generic input device table -- rarely relevant",
    "[Keyboard]":             "keyboard table -- rarely relevant",
    "[Pointing Device]":      "pointing device table -- rarely relevant",
    "[Modem]":                "modem table -- rarely relevant",
    "[Network]":              "network section header -- sub-sections stripped",
    "[Adapter]":              "network adapter details including IP/MAC -- PII",
    "[Protocol]":             "network protocol table -- rarely relevant",
    "[WinSock]":              "WinSock table -- rarely relevant",
    "[Ports]":                "ports section header -- sub-sections stripped",
    "[Serial]":               "serial port table -- rarely relevant",
    "[Parallel]":             "parallel port table -- rarely relevant",
    "[Storage]":              "storage section header -- sub-sections stripped",
    "[Drives]":               "drive/volume listing with volume serials -- PII",
    "[Disks]":                "physical disk details -- rarely relevant",
    "[SCSI]":                 "SCSI device table -- rarely relevant",
    "[IDE]":                  "IDE controller table -- rarely relevant",
    "[Printing]":             "printing table -- rarely relevant",
    "[USB]":                  "USB device table -- rarely relevant",
    "[Software Environment]": "software inventory (running tasks, loaded modules, services, startup programs, env vars, network connections, OLE/COM, WER) -- exposes installed software footprint",
    "[System Drivers]":       "loaded kernel driver list -- exposes installed software footprint",
    "[Environment Variables]":"environment variables -- may contain developer paths and secrets",
    "[Print Jobs]":           "print job queue -- rarely relevant",
    "[Network Connections]":  "active network connections -- PII",
    "[Running Tasks]":        "running process list -- exposes installed software footprint",
    "[Loaded Modules]":       "loaded DLL/module list -- exposes installed software footprint",
    "[Services]":             "service list -- exposes installed software footprint",
    "[Program Groups]":       "program groups/Start Menu -- rarely relevant",
    "[Startup Programs]":     "startup program list -- exposes installed software footprint",
    "[OLE Registration]":     "COM/OLE registration table -- rarely relevant",
    "[Windows Error Reporting]": "WER report list -- rarely relevant",
}

# Generic reason for a stripped section not named above.
DEFAULT_STRIP_REASON = "stripped by default (low-relevance or potentially sensitive)"

# Every section name the tool knows about (used to resolve --include/--exclude
# tokens and to drive --list-sections).
KNOWN_SECTIONS = set(KEEP_SECTIONS) | set(STRIP_REASONS.keys())

# PII redaction rules: list of (compiled_regex, replacement_token) pairs.
# Applied to every line in kept sections.  Order matters: specific first.
PII_RULES = [
    # Hostname -- match "System Name<TAB>VALUE" or "System Name: VALUE"
    (re.compile(r'(?i)(System Name[\t:]\s*)(\S+)'),           r'\1[REDACTED-HOSTNAME]'),
    # User Name field -- redact only if not "Not Available"
    (re.compile(r'(?i)(User Name[\t:]\s*)(?!Not Available)(.+)'), r'\1[REDACTED-USER]'),
    # Registered Owner / Organization
    (re.compile(r'(?i)(Registered (Owner|Organization)[\t:]\s*)(.+)'), r'\1[REDACTED]'),
    # Windows Product ID / product key
    (re.compile(r'(?i)(Windows Product (ID|Key)[\t:]\s*)(.+)'), r'\1[REDACTED-PRODUCT-ID]'),
    # Standalone product ID pattern (XXXXX-XXXXX-...)
    (re.compile(r'\b([A-Z0-9]{5}-){2,}[A-Z0-9]{5}\b'),       r'[REDACTED-PRODUCT-KEY]'),
    # SMBIOS UUID (8-4-4-4-12 hex)
    (re.compile(r'\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b'),
                                                               r'[REDACTED-UUID]'),
    # Serial number fields
    (re.compile(r'(?i)(Serial Number[\t:]\s*)(.+)'),           r'\1[REDACTED-SERIAL]'),
    # Volume serial numbers
    (re.compile(r'(?i)(Volume Serial Number[\t:]\s*)([0-9A-Fa-f]+)'), r'\1[REDACTED-SERIAL]'),
    # MAC addresses (with : or - separators, optionally wrapped in special chars)
    (re.compile(r'[\?\*\s]*([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}[\?\*\s]*'), r'[REDACTED-MAC]'),
    # IP Address / Subnet / Gateway / DHCP Server fields
    (re.compile(r'(?i)(IP Address[\t:]\s*)(\d[\d\.]+)'),      r'\1[REDACTED-IP]'),
    (re.compile(r'(?i)(IP Subnet[\t:]\s*)(\d[\d\.]+)'),       r'\1[REDACTED-IP]'),
    (re.compile(r'(?i)((Default IP |DHCP )Gateway[\t:]\s*)(\d[\d\.]+)'), r'\1[REDACTED-IP]'),
    (re.compile(r'(?i)(DHCP Server[\t:]\s*)(\d[\d\.]+)'),     r'\1[REDACTED-IP]'),
    # User profile paths  C:\Users\<name>\...
    (re.compile(r'(?i)(C:\\Users\\)([^\\]+)(\\?)'),           r'C:\\Users\\[REDACTED-USER]\3'),
    # Report header line hostname ("System Name: HOSTNAME")
    (re.compile(r'^(System Name:\s*)(\S+)'),                   r'\1[REDACTED-HOSTNAME]'),
]

# Rows in [System Summary] surfaced first (OS identity), then hardware.
# Everything in System Summary is kept; these lists only drive ordering.
OS_IDENTITY_KEYS = [
    "OS Name",
    "Version",
    "OS Manufacturer",
    "Other OS Description",
    "System Type",
    "Locale",
    "Hardware Abstraction Layer",
    "Time Zone",
    "Windows Feature Experience Pack",
]

HARDWARE_IDENTITY_KEYS = [
    "System Manufacturer",
    "System Model",
    "System SKU",
    "Processor",
    "BIOS Version/Date",
    "SMBIOS Version",
    "Embedded Controller Version",
    "BIOS Mode",
    "BaseBoard Manufacturer",
    "BaseBoard Product",
    "BaseBoard Version",
    "Platform Role",
    "Secure Boot State",
    "PCR7 Configuration",
]

# ---------------------------------------------------------------------------
# END CONFIG
# ---------------------------------------------------------------------------


def normalize_token(text):
    """Normalize a section name/token for loose matching: lowercase and drop
    every non-alphanumeric character (brackets, spaces, hyphens, slashes).

    So "[System Drivers]", "System Drivers", and "SystemDrivers" all collapse
    to "systemdrivers".
    """
    return re.sub(r'[^a-z0-9]', '', text.lower())


def build_section_lookup(headers):
    """Map normalized token -> canonical bracketed header for a set of headers."""
    return {normalize_token(h): h for h in headers}


def split_section_tokens(values):
    """Flatten a list of (possibly comma-separated, possibly repeated) flag
    values into a clean list of individual tokens.
    """
    tokens = []
    for value in values or []:
        for part in value.split(','):
            part = part.strip()
            if part:
                tokens.append(part)
    return tokens


def resolve_section_tokens(tokens, lookup):
    """Resolve user tokens to canonical headers.

    Returns (resolved_set, unknown_list).  unknown_list preserves the raw
    tokens that did not match any known or in-file section.
    """
    resolved = set()
    unknown = []
    for raw in tokens:
        key = normalize_token(raw)
        if key in lookup:
            resolved.add(lookup[key])
        else:
            unknown.append(raw)
    return resolved, unknown


def resolve_keep_sections(section_order, include_tokens, exclude_tokens):
    """Compute the effective keep-set from defaults + --include/--exclude.

    Tokens are resolved against the known-section catalog AND the sections
    actually present in the file, so a user can name any real section.

    Returns (keep_set, errors) where errors is a list of human-readable
    strings; a non-empty errors list means the run should abort before
    writing output.
    """
    lookup = build_section_lookup(KNOWN_SECTIONS | set(section_order))

    inc, inc_unknown = resolve_section_tokens(include_tokens, lookup)
    exc, exc_unknown = resolve_section_tokens(exclude_tokens, lookup)

    errors = []
    if inc_unknown:
        errors.append("Unrecognized --include section(s): " + ", ".join(inc_unknown))
    if exc_unknown:
        errors.append("Unrecognized --exclude section(s): " + ", ".join(exc_unknown))

    conflict = inc & exc
    if conflict:
        names = ", ".join(sorted(conflict))
        errors.append("Section(s) listed in BOTH --include and --exclude: " + names)

    keep = (set(KEEP_SECTIONS) | inc) - exc
    return keep, errors


def normalize_section_header(line):
    """Return the canonical '[Section Name]' form if this line is a header, else None."""
    s = line.strip()
    if s.startswith('[') and s.endswith(']'):
        return s
    return None


def apply_pii_rules(line, extra_rules=None):
    """Apply all PII_RULES substitutions to a single text line.

    ``extra_rules`` is an optional list of (compiled_regex, replacement)
    pairs derived at runtime (e.g. the live hostname); they run after the
    static rules.
    """
    for pattern, replacement in PII_RULES:
        line = pattern.sub(replacement, line)
    for pattern, replacement in (extra_rules or ()):
        line = pattern.sub(replacement, line)
    return line


def build_dynamic_rules(hostname):
    """Build PII rules that depend on runtime state.

    The static PII_RULES only redact the hostname where it appears in a
    labeled field ("System Name<TAB>..."). When normally-stripped sections
    are force-included via --include, the bare hostname shows up scattered
    through driver paths and environment-variable values; this rule scrubs
    those bare occurrences too. Guarded on length >= 4 to avoid redacting a
    short hostname that collides with common words.
    """
    rules = []
    if hostname and len(hostname) >= 4:
        rules.append(
            (re.compile(r'(?i)\b' + re.escape(hostname) + r'\b'), '[REDACTED-HOSTNAME]')
        )
    return rules


def to_ascii_safe(text):
    """
    Replace non-ASCII characters with the closest ASCII equivalent or '?' so
    the output is safe on Windows codepage 437/1252 terminals.  The msinfo
    file can contain invisible Unicode directional marks -- strip those
    silently first.
    """
    # Remove Unicode directional / zero-width / BOM marks (escaped codepoints
    # so this source stays plain-ASCII and encoding-agnostic):
    #   U+200B-U+200F zero-width + LTR/RTL marks, U+202A-U+202E embeddings,
    #   U+FEFF zero-width no-break space / BOM.
    text = re.sub('[\u200b-\u200f\u202a-\u202e\ufeff]', '', text)
    return text.encode('ascii', errors='replace').decode('ascii')


def parse_key_value(line):
    """Return (key, rest) if line is a TAB-separated key-value row, else (None, None)."""
    if '\t' in line:
        key, _, rest = line.partition('\t')
        return key.strip(), rest
    return None, None


def build_section_map(lines):
    """
    Parse the file into a dict: section_header -> list of raw text lines
    (not including the header line itself).
    Returns (preamble_lines, section_map, section_order).
    preamble_lines are lines before the first section header.
    """
    preamble = []
    sections = {}     # header -> [lines]
    order = []        # preserves encounter order
    current = None

    for line in lines:
        stripped = line.rstrip('\r\n')
        header = normalize_section_header(stripped)
        if header:
            current = header
            if current not in sections:
                sections[current] = []
                order.append(current)
        elif current is None:
            preamble.append(stripped)
        else:
            sections[current].append(stripped)

    return preamble, sections, order


def reorder_system_summary(body_lines):
    """
    Reorder [System Summary] rows so OS-identity rows appear first,
    then hardware rows, then anything else.
    The 'Item<TAB>Value' header row and blank lines are handled specially.
    """
    header_row = None
    os_rows = []
    hw_rows = []
    other_rows = []

    for line in body_lines:
        if line.strip() == 'Item\tValue' or line.strip() == '':
            if line.strip() == 'Item\tValue':
                header_row = line
            continue
        key, _ = parse_key_value(line)
        if key is None:
            other_rows.append(line)
            continue
        matched = False
        for k in OS_IDENTITY_KEYS:
            if key.lower().startswith(k.lower()):
                os_rows.append(line)
                matched = True
                break
        if not matched:
            for k in HARDWARE_IDENTITY_KEYS:
                if key.lower().startswith(k.lower()):
                    hw_rows.append(line)
                    matched = True
                    break
        if not matched:
            other_rows.append(line)

    result = []
    if header_row:
        result.append(header_row)
    result.append('')
    result.append('--- OS Identity ---')
    result.extend(os_rows)
    result.append('')
    result.append('--- Hardware Identity ---')
    result.extend(hw_rows)
    result.append('')
    result.append('--- Other System Information ---')
    result.extend(other_rows)
    return result


def emit_stripped_placeholder(header):
    """Return a single placeholder line for a stripped section."""
    reason = STRIP_REASONS.get(header, DEFAULT_STRIP_REASON)
    section_name = header[1:-1]   # remove brackets for display
    return f"[{section_name}]  -- REMOVED ({reason})"


def read_sections(input_path):
    """Read and parse the msinfo export.  Returns (total_in, preamble, sections, order)."""
    with open(input_path, 'r', encoding='utf-16') as fh:
        raw_lines = fh.readlines()
    preamble, sections, order = build_section_map(raw_lines)
    return len(raw_lines), preamble, sections, order


def render(preamble, sections, section_order, keep_sections, extra_rules=None):
    """Build the redacted output lines from parsed sections and a keep-set."""
    out_lines = []

    # --- Preamble (report header line) ---
    for line in preamble:
        out_lines.append(to_ascii_safe(apply_pii_rules(line, extra_rules)))

    # --- System Summary first (reordered), only if kept ---
    summary_emitted = False
    if "[System Summary]" in keep_sections and "[System Summary]" in sections:
        out_lines.append('')
        out_lines.append('[System Summary]')
        out_lines.append('')
        body = [to_ascii_safe(apply_pii_rules(l, extra_rules)) for l in sections["[System Summary]"]]
        out_lines.extend(reorder_system_summary(body))
        summary_emitted = True

    # --- Remaining sections in encounter order ---
    for section in section_order:
        if section == "[System Summary]" and summary_emitted:
            continue   # already emitted above

        if section not in keep_sections:
            # Emit stripped placeholder (deduplicate consecutive same-section strips)
            placeholder = emit_stripped_placeholder(section)
            if not out_lines or out_lines[-1] != placeholder:
                out_lines.append('')
                out_lines.append(placeholder)
            continue

        # Kept section
        out_lines.append('')
        out_lines.append(section)
        out_lines.append('')
        for line in sections[section]:
            out_lines.append(to_ascii_safe(apply_pii_rules(line, extra_rules)))

    return out_lines


def write_output(out_lines, output_path):
    """Write the rendered lines as UTF-8 with CRLF endings.  Returns line count."""
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    with open(output_path, 'w', encoding='utf-8', newline='\r\n') as fh:
        for line in out_lines:
            fh.write(line + '\n')
    return len(out_lines)


def verify(output_path, hostname=None):
    """
    Run post-generation verification checks and print a concise report.
    Returns True if all checks pass.
    """
    print("")
    print("[VERIFY] Running self-verification checks...")
    with open(output_path, 'r', encoding='utf-8') as fh:
        content = fh.read()
        lines_out = content.splitlines()

    ok = True

    # 1. OS Name line should exist (informational)
    os_name_lines = [l for l in lines_out if l.startswith('OS Name')]
    if os_name_lines:
        print(f"[OK   ] OS Name: {os_name_lines[0]}")
    else:
        print("[WARN ] OS Name row not found in output")

    # Version
    ver_lines = [l for l in lines_out if l.startswith('Version\t')]
    if ver_lines:
        print(f"[OK   ] Version: {ver_lines[0]}")
    else:
        print("[WARN ] Version row not found")

    # 2. Software Environment must not appear as real content
    se_real = [l for l in lines_out if '[Software Environment]' in l and 'REMOVED' not in l]
    if se_real:
        print(f"[WARN ] [Software Environment] appears as real content ({len(se_real)} lines) "
              f"-- expected only if you --include'd it")

    # 3. Hostname must not appear unredacted (case-insensitive)
    if hostname:
        hn_bare = len(re.findall(r'(?<!\[REDACTED-)' + re.escape(hostname), content, re.IGNORECASE))
        if hn_bare > 0:
            print(f"[FAIL ] Hostname '{hostname}' found unredacted ({hn_bare} occurrences)")
            ok = False
        else:
            print(f"[OK   ] Hostname '{hostname}' does not appear unredacted")

    # 4. No real MAC addresses remain
    mac_pat = re.compile(r'(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}')
    mac_hits = mac_pat.findall(content)
    if mac_hits:
        print(f"[FAIL ] MAC address pattern found: {mac_hits[:3]}")
        ok = False
    else:
        print("[OK   ] No MAC addresses found")

    # 5. No real IP addresses remain in IP field lines
    ip_field_pat = re.compile(r'(?i)(IP Address|IP Subnet|Gateway|DHCP Server)[\t:]\s*\d[\d\.]+')
    ip_field_hits = ip_field_pat.findall(content)
    if ip_field_hits:
        print(f"[FAIL ] IP address field with real value found: {ip_field_hits[:3]}")
        ok = False
    else:
        print("[OK   ] No real IP addresses in IP field lines")

    # 6. Volume serial numbers must be gone
    vol_serial_pat = re.compile(r'(?i)Volume Serial Number[\t:]\s*[0-9A-Fa-f]{6,}')
    vs_hits = vol_serial_pat.findall(content)
    if vs_hits:
        print(f"[FAIL ] Volume serial numbers found: {vs_hits[:3]}")
        ok = False
    else:
        print("[OK   ] No volume serial numbers found")

    # 7. User Name field must not have a real value
    user_field_pat = re.compile(r'(?i)User Name[\t:]\s*(?!Not Available|\[REDACTED)(\S.+)')
    user_hits = user_field_pat.findall(content)
    if user_hits:
        print(f"[FAIL ] User Name field has real value: {user_hits[:3]}")
        ok = False
    else:
        print("[OK   ] User Name field clean")

    print("")
    if ok:
        print("[OK   ] All verification checks passed.")
    else:
        print("[FAIL ] One or more verification checks failed -- review output.")

    return ok


def print_section_catalog():
    """Print every known section with its default disposition (for --list-sections)."""
    print("Default-KEPT sections (emitted verbatim, with PII redaction):")
    for header in sorted(KEEP_SECTIONS):
        print(f"  KEEP   {header}")
    print("")
    print("Default-STRIPPED sections (replaced with a one-line placeholder):")
    for header, reason in STRIP_REASONS.items():
        if header in KEEP_SECTIONS:
            continue
        print(f"  STRIP  {header}")
        print(f"           {reason}")
    print("")
    print("Pass any section name to --include (force keep) or --exclude (force strip).")
    print("Matching ignores case, spaces, and brackets, e.g.:")
    print("  --include SystemDrivers,EnvironmentVariables")
    print('  --exclude Services,"Program Groups"')


def default_output_path(input_path):
    """Sidecar next to the input: <stem>.redacted<suffix> (e.g. msinfo.redacted.txt)."""
    p = Path(input_path)
    return str(p.with_name(f"{p.stem}.redacted{p.suffix}"))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="dz redact-msinfo",
        description=(
            "Redact a Windows msinfo32 text export (section stripping + PII "
            "scrubbing) for safe sharing. Choose sections with --include / "
            "--exclude; otherwise sensible defaults apply."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--input', help='Input path (UTF-16 LE msinfo32 .txt). Required unless --list-sections.')
    parser.add_argument('--output', help='Output path (UTF-8 cleaned .txt). Default: <input-stem>.redacted<.ext> beside the input.')
    parser.add_argument('--include', action='append', metavar='SECTIONS',
                        help='Comma-separated section(s) to KEEP in addition to the defaults '
                             '(repeatable). E.g. --include SystemDrivers,EnvironmentVariables')
    parser.add_argument('--exclude', action='append', metavar='SECTIONS',
                        help='Comma-separated section(s) to STRIP even if kept by default '
                             '(repeatable). E.g. --exclude Display,ProblemDevices')
    parser.add_argument('--list-sections', action='store_true',
                        help='List every known section with its default disposition, then exit.')
    parser.add_argument('--hostname', default=None,
                        help='Hostname to verify was redacted (default: this machine\'s hostname).')
    parser.add_argument('--no-verify', action='store_true', help='Skip the self-verification step.')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_sections:
        print_section_catalog()
        return 0

    if not args.input:
        print("[ERROR] --input is required (or use --list-sections).", file=sys.stderr)
        return 2

    if not os.path.isfile(args.input):
        print(f"[ERROR] Input file not found: {args.input}", file=sys.stderr)
        return 1

    output_path = args.output or default_output_path(args.input)

    if os.path.realpath(args.input) == os.path.realpath(output_path):
        print("[ERROR] Input and output are the same file -- refusing to overwrite input.", file=sys.stderr)
        return 1

    include_tokens = split_section_tokens(args.include)
    exclude_tokens = split_section_tokens(args.exclude)

    hostname = args.hostname if args.hostname is not None else socket.gethostname()
    extra_rules = build_dynamic_rules(hostname)

    print(f"[READ ] {args.input}")
    total_in, preamble, sections, section_order = read_sections(args.input)
    print(f"[INFO ] Input: {total_in} lines, encoding UTF-16 LE")

    keep_sections, errors = resolve_keep_sections(section_order, include_tokens, exclude_tokens)
    if errors:
        for e in errors:
            print(f"[ERROR] {e}", file=sys.stderr)
        print("[ERROR] Run 'dz redact-msinfo --list-sections' to see valid section names.", file=sys.stderr)
        return 1

    # Warn when normally-stripped sections are force-included: the PII
    # scrubber is tuned for the default kept sections and cannot redact
    # arbitrary secrets (API keys, tokens, passwords, account names) that
    # live in sections like [Environment Variables] or [Running Tasks].
    forced_in = sorted(keep_sections - set(KEEP_SECTIONS))
    if forced_in:
        print(f"[WARN ] Force-including default-stripped section(s): {forced_in}")
        print("[WARN ] PII scrubbing is tuned for the default sections; included")
        print("[WARN ] sections may still contain secrets/PII the scrubber cannot")
        print("[WARN ] detect (API keys, tokens, account names). REVIEW the output.")

    out_lines = render(preamble, sections, section_order, keep_sections, extra_rules)
    total_out = write_output(out_lines, output_path)

    stripped_all = [s for s in section_order if s not in keep_sections]
    print(f"[WRITE] {output_path}")
    print(f"[INFO ] Output: {total_out} lines (from {total_in})")
    print(f"[INFO ] Kept sections  : {sorted(keep_sections)}")
    print(f"[INFO ] Stripped count : {len(stripped_all)} sections")

    if not args.no_verify:
        ok = verify(output_path, hostname=hostname)
        return 0 if ok else 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
