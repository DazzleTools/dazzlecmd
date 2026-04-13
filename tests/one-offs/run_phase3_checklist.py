"""
Phase 3 Human Test Checklist - Automated Runner
Executes Sections 1-10 of v0.7.11__Phase3__kit-management-and-config-write.md

Uses subprocess for clean isolation with DAZZLECMD_CONFIG env var.
"""

import json
import os
import subprocess
import sys
import tempfile
import traceback

CWD = r"C:\code\dazzlecmd\github"
PYTHON = sys.executable
CONFIG_PATH = os.path.join(tempfile.gettempdir(), "dz-tester-agent-config.json")

# Build env with isolation
BASE_ENV = {**os.environ, "DAZZLECMD_CONFIG": CONFIG_PATH}
# Remove DZ_KITS if set to avoid interference
BASE_ENV.pop("DZ_KITS", None)


class TestResult:
    def __init__(self, test_id, description, status, details="", stdout="", stderr=""):
        self.test_id = test_id
        self.description = description
        self.status = status  # PASS, FAIL, REVIEW, MANUAL, SKIP
        self.details = details
        self.stdout = stdout
        self.stderr = stderr


results = []


def dz(*args, env=None, input_text=None):
    """Run a dz command via python -m dazzlecmd, return (returncode, stdout, stderr)."""
    cmd = [PYTHON, "-m", "dazzlecmd"] + list(args)
    use_env = env if env is not None else BASE_ENV
    r = subprocess.run(
        cmd, capture_output=True, text=True, cwd=CWD, env=use_env,
        input=input_text, timeout=30
    )
    return r.returncode, r.stdout, r.stderr


def reset():
    """Reset config by deleting the file and running dz kit reset --yes."""
    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)
    # Also run reset for good measure (may fail if file already gone)
    dz("kit", "reset", "--yes")


def read_config():
    """Read and parse the config file, return dict or None."""
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def write_config(data):
    """Write data to config file as JSON."""
    os.makedirs(os.path.dirname(CONFIG_PATH) or ".", exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def add_result(test_id, desc, status, details="", stdout="", stderr=""):
    results.append(TestResult(test_id, desc, status, details, stdout, stderr))
    symbol = {"PASS": "[OK]", "FAIL": "[FAIL]", "REVIEW": "[REVIEW]", "MANUAL": "[MANUAL]", "SKIP": "[SKIP]"}
    print(f"  {symbol.get(status, '???')} {test_id}: {desc} -> {status}")
    if status == "FAIL":
        print(f"       Details: {details[:200]}")


# ============================================================
# SECTION 1: Config file creation and schema
# ============================================================
def run_section_1():
    print("\n=== SECTION 1: Config file creation and schema ===")

    # 1.1 First-time config creation
    reset()
    rc, out, err = dz("kit", "enable", "wtf")
    cfg = read_config()
    if rc == 0 and "Enabled kit: wtf" in out and cfg is not None:
        if cfg.get("_schema_version") == 1 and "wtf" in cfg.get("active_kits", []):
            add_result("1.1", "First-time config creation", "PASS",
                       stdout=out, stderr=err)
        else:
            add_result("1.1", "First-time config creation", "FAIL",
                       f"Config content wrong: {cfg}", stdout=out, stderr=err)
    else:
        add_result("1.1", "First-time config creation", "FAIL",
                   f"rc={rc}, out={out!r}, err={err!r}, cfg_exists={cfg is not None}",
                   stdout=out, stderr=err)

    # 1.2 Schema version stays put across writes
    rc, out, err = dz("kit", "disable", "dazzletools")
    cfg = read_config()
    if cfg and cfg.get("_schema_version") == 1 and "dazzletools" in cfg.get("disabled_kits", []):
        if "wtf" in cfg.get("active_kits", []):
            add_result("1.2", "Schema version stays put across writes", "PASS",
                       stdout=out, stderr=err)
        else:
            add_result("1.2", "Schema version stays put across writes", "FAIL",
                       f"active_kits missing wtf: {cfg}", stdout=out, stderr=err)
    else:
        add_result("1.2", "Schema version stays put across writes", "FAIL",
                   f"cfg={cfg}", stdout=out, stderr=err)

    # 1.3 Hand-editable: unknown keys preserved
    reset()
    write_config({
        "_schema_version": 1,
        "kit_precedence": ["core"],
        "my_custom_user_key": "do not touch"
    })
    rc, out, err = dz("kit", "enable", "wtf")
    cfg = read_config()
    if cfg and cfg.get("my_custom_user_key") == "do not touch":
        if "wtf" in cfg.get("active_kits", []) and cfg.get("kit_precedence") == ["core"]:
            add_result("1.3", "Unknown keys preserved", "PASS",
                       stdout=out, stderr=err)
        else:
            add_result("1.3", "Unknown keys preserved", "FAIL",
                       f"active_kits or kit_precedence wrong: {cfg}", stdout=out, stderr=err)
    else:
        add_result("1.3", "Unknown keys preserved", "FAIL",
                   f"my_custom_user_key lost: {cfg}", stdout=out, stderr=err)

    # 1.4 Malformed config is tolerated
    reset()
    with open(CONFIG_PATH, "w") as f:
        f.write("{ not json")
    rc, out, err = dz("list")
    if rc == 0 or "tool(s)" in out.lower() or "tools" in out.lower():
        if "warning" in err.lower() or "could not read" in err.lower() or "could not parse" in err.lower():
            add_result("1.4", "Malformed config is tolerated", "PASS",
                       f"Warning present and list worked", stdout=out, stderr=err)
        else:
            # List worked but no warning - maybe warning is on stdout?
            combined = out + err
            if "warning" in combined.lower():
                add_result("1.4", "Malformed config is tolerated", "PASS",
                           f"Warning found in combined output", stdout=out, stderr=err)
            else:
                add_result("1.4", "Malformed config is tolerated", "REVIEW",
                           f"List ran but no warning about malformed config seen",
                           stdout=out, stderr=err)
    else:
        add_result("1.4", "Malformed config is tolerated", "FAIL",
                   f"dz list crashed or no output. rc={rc}", stdout=out, stderr=err)

    # 1.5 Reset with confirmation (interactive prompt)
    add_result("1.5", "Reset with confirmation (interactive prompt)", "MANUAL",
               "Requires interactive stdin to type 'n' at prompt")

    # 1.6 Reset with --yes actually deletes
    reset()
    dz("kit", "enable", "wtf")
    assert os.path.exists(CONFIG_PATH), "Config should exist before reset"
    rc, out, err = dz("kit", "reset", "--yes")
    if not os.path.exists(CONFIG_PATH) and "Config cleared" in out:
        add_result("1.6", "Reset with --yes actually deletes", "PASS",
                   stdout=out, stderr=err)
    elif not os.path.exists(CONFIG_PATH):
        add_result("1.6", "Reset with --yes actually deletes", "PASS",
                   f"File deleted. Output: {out!r}", stdout=out, stderr=err)
    else:
        add_result("1.6", "Reset with --yes actually deletes", "FAIL",
                   f"Config file still exists. rc={rc}", stdout=out, stderr=err)


# ============================================================
# SECTION 2: Kit enable / disable / focus
# ============================================================
def run_section_2():
    print("\n=== SECTION 2: Kit enable / disable / focus ===")
    reset()

    # 2.1 Enable an unknown kit
    rc, out, err = dz("kit", "enable", "ghost-kit-does-not-exist")
    if rc == 0 and "Enabled kit: ghost-kit-does-not-exist" in out:
        cfg = read_config()
        if "ghost-kit-does-not-exist" in cfg.get("active_kits", []):
            if "warning" in err.lower() or "not found" in err.lower():
                add_result("2.1", "Enable unknown kit (warn, not fail)", "PASS",
                           stdout=out, stderr=err)
            else:
                combined = out + err
                if "warning" in combined.lower() or "not found" in combined.lower():
                    add_result("2.1", "Enable unknown kit (warn, not fail)", "PASS",
                               f"Warning in combined output", stdout=out, stderr=err)
                else:
                    add_result("2.1", "Enable unknown kit (warn, not fail)", "REVIEW",
                               f"Enabled ok but no warning about unknown kit",
                               stdout=out, stderr=err)
        else:
            add_result("2.1", "Enable unknown kit (warn, not fail)", "FAIL",
                       f"Not in active_kits: {cfg}", stdout=out, stderr=err)
    else:
        add_result("2.1", "Enable unknown kit (warn, not fail)", "FAIL",
                   f"rc={rc}", stdout=out, stderr=err)

    # 2.2 Disable hides tools from dz list
    reset()
    rc1, out1, err1 = dz("list")
    # Count tools in first listing
    import re
    match1 = re.search(r'(\d+)\s+tool\(s\)', out1)
    n1 = int(match1.group(1)) if match1 else -1

    dz("kit", "disable", "dazzletools")
    rc2, out2, err2 = dz("list")
    match2 = re.search(r'(\d+)\s+tool\(s\)', out2)
    n2 = int(match2.group(1)) if match2 else -1

    if n1 > 0 and n2 >= 0 and n2 < n1:
        # Also check that dazzletools tools are gone
        dt_tools = ["dos2unix", "split", "github", "claude-cleanup"]
        dt_present = [t for t in dt_tools if t in out2.lower()]
        if not dt_present:
            add_result("2.2", "Disable hides tools from dz list", "PASS",
                       f"Before: {n1} tools, After: {n2} tools", stdout=out2, stderr=err2)
        else:
            add_result("2.2", "Disable hides tools from dz list", "FAIL",
                       f"dazzletools tools still visible: {dt_present}",
                       stdout=out2, stderr=err2)
    else:
        add_result("2.2", "Disable hides tools from dz list", "FAIL",
                   f"Tool counts: before={n1}, after={n2}", stdout=out2, stderr=err2)

    # 2.3 always_active kits still start enabled
    reset()
    rc, out, err = dz("kit", "list")
    out_lower = out.lower()
    if "core" in out_lower and "always active" in out_lower:
        if "dazzletools" in out_lower:
            add_result("2.3", "always_active kits start enabled", "PASS",
                       stdout=out, stderr=err)
        else:
            add_result("2.3", "always_active kits start enabled", "REVIEW",
                       "core shows always_active but dazzletools not found",
                       stdout=out, stderr=err)
    else:
        add_result("2.3", "always_active kits start enabled", "FAIL",
                   f"core/always_active not in output", stdout=out, stderr=err)

    # 2.4 Explicit disable overrides always_active
    reset()
    dz("kit", "disable", "core")
    rc, out, err = dz("list")
    core_tools = ["fixpath", "find"]
    core_present = [t for t in core_tools if re.search(r'\b' + t + r'\b', out)]
    rc2, out2, err2 = dz("kit", "list")

    if not core_present:
        cfg = read_config()
        if "core" in cfg.get("disabled_kits", []):
            if "disabled" in out2.lower():
                add_result("2.4", "Explicit disable overrides always_active", "PASS",
                           stdout=out, stderr=err)
            else:
                add_result("2.4", "Explicit disable overrides always_active", "REVIEW",
                           f"Core hidden from list, but kit list output uncertain",
                           stdout=out2, stderr=err2)
        else:
            add_result("2.4", "Explicit disable overrides always_active", "FAIL",
                       f"core not in disabled_kits: {cfg}", stdout=out, stderr=err)
    else:
        add_result("2.4", "Explicit disable overrides always_active", "FAIL",
                   f"Core tools still visible: {core_present}", stdout=out, stderr=err)

    # Cleanup 2.4
    dz("kit", "enable", "core")

    # 2.5 Focus preserves always_active kits
    reset()
    rc, out, err = dz("kit", "focus", "wtf")
    out_lower = out.lower()
    if "focus" in out_lower or "preserved" in out_lower or "always_active" in out_lower:
        cfg = read_config()
        if cfg:
            disabled = cfg.get("disabled_kits", [])
            if "core" not in disabled and "dazzletools" not in disabled:
                # Verify dz list still shows core tools
                rc2, out2, err2 = dz("list")
                if "fixpath" in out2.lower() or "find" in out2.lower():
                    add_result("2.5", "Focus preserves always_active kits", "PASS",
                               stdout=out, stderr=err)
                else:
                    add_result("2.5", "Focus preserves always_active kits", "FAIL",
                               f"Core tools not in dz list after focus",
                               stdout=out2, stderr=err2)
            else:
                add_result("2.5", "Focus preserves always_active kits", "FAIL",
                           f"core or dazzletools in disabled_kits: {disabled}",
                           stdout=out, stderr=err)
        else:
            add_result("2.5", "Focus preserves always_active kits", "FAIL",
                       "Config is None after focus", stdout=out, stderr=err)
    else:
        add_result("2.5", "Focus preserves always_active kits", "REVIEW",
                   f"Output doesn't mention focus/preserved/always_active clearly",
                   stdout=out, stderr=err)

    # 2.6 Overlap warning (disabled wins)
    reset()
    write_config({
        "_schema_version": 1,
        "active_kits": ["wtf"],
        "disabled_kits": ["wtf"]
    })
    rc, out, err = dz("list")
    combined = out + err
    if "warning" in combined.lower() and ("disabled wins" in combined.lower() or "both active_kits and disabled_kits" in combined.lower()):
        # Check wtf tools are NOT shown
        if "locked" not in out.lower() and "restarted" not in out.lower():
            add_result("2.6", "Overlap warning (disabled wins)", "PASS",
                       stdout=out, stderr=err)
        else:
            # wtf tools: locked, restarted. Check if they show up
            add_result("2.6", "Overlap warning (disabled wins)", "REVIEW",
                       "Warning present but wtf tools may still be visible",
                       stdout=out, stderr=err)
    else:
        # Check if wtf tools are hidden (even without warning)
        if "locked" not in out and "restarted" not in out:
            add_result("2.6", "Overlap warning (disabled wins)", "REVIEW",
                       "No warning seen, but wtf tools appear hidden. Check manually.",
                       stdout=out, stderr=err)
        else:
            add_result("2.6", "Overlap warning (disabled wins)", "FAIL",
                       f"No overlap warning and wtf tools may be visible",
                       stdout=out, stderr=err)


# ============================================================
# SECTION 3: DZ_KITS environment variable
# ============================================================
def run_section_3():
    print("\n=== SECTION 3: DZ_KITS environment variable ===")
    reset()

    # 3.1 Full override
    dz("kit", "enable", "wtf")
    env_override = {**BASE_ENV, "DZ_KITS": "core"}
    rc, out, err = dz("list", env=env_override)
    import re
    # Check that only core tools appear
    has_wtf_tools = any(t in out.lower() for t in ["locked", "restarted"])
    has_core_tools = any(t in out.lower() for t in ["fixpath", "find"])
    if has_core_tools and not has_wtf_tools:
        add_result("3.1", "DZ_KITS full override", "PASS",
                   stdout=out, stderr=err)
    else:
        add_result("3.1", "DZ_KITS full override", "FAIL",
                   f"core_tools={has_core_tools}, wtf_tools={has_wtf_tools}",
                   stdout=out, stderr=err)

    # 3.2 Empty DZ_KITS means no kits
    env_empty = {**BASE_ENV, "DZ_KITS": ""}
    rc, out, err = dz("list", env=env_empty)
    if "no tools" in out.lower() or "0 tool" in out.lower():
        add_result("3.2a", "Empty DZ_KITS = no kits (dz list)", "PASS",
                   stdout=out, stderr=err)
    else:
        add_result("3.2a", "Empty DZ_KITS = no kits (dz list)", "REVIEW",
                   f"Expected 'no tools' message", stdout=out, stderr=err)

    rc2, out2, err2 = dz("kit", "list", env=env_empty)
    if rc2 == 0:
        add_result("3.2b", "Empty DZ_KITS: meta-command still works", "PASS",
                   stdout=out2, stderr=err2)
    else:
        add_result("3.2b", "Empty DZ_KITS: meta-command still works", "FAIL",
                   f"rc={rc2}", stdout=out2, stderr=err2)

    # 3.3 DZ_KITS empty vs unset are different
    env_unset = {k: v for k, v in BASE_ENV.items() if k != "DZ_KITS"}
    rc_unset, out_unset, err_unset = dz("list", env=env_unset)
    rc_empty, out_empty, err_empty = dz("list", env=env_empty)

    match_unset = re.search(r'(\d+)\s+tool\(s\)', out_unset)
    match_empty = re.search(r'(\d+)\s+tool\(s\)', out_empty)
    n_unset = int(match_unset.group(1)) if match_unset else -1
    n_empty = int(match_empty.group(1)) if match_empty else 0

    if n_unset > 0 and n_empty == 0:
        add_result("3.3", "DZ_KITS empty vs unset are different", "PASS",
                   f"unset={n_unset} tools, empty={n_empty} tools")
    elif n_unset > n_empty:
        add_result("3.3", "DZ_KITS empty vs unset are different", "PASS",
                   f"unset={n_unset} tools, empty={n_empty} tools (empty has fewer)")
    else:
        add_result("3.3", "DZ_KITS empty vs unset are different", "FAIL",
                   f"unset={n_unset}, empty={n_empty} -- should differ",
                   stdout=out_empty, stderr=err_empty)


# ============================================================
# SECTION 4: dz tree visualization
# ============================================================
def run_section_4():
    print("\n=== SECTION 4: dz tree visualization ===")
    reset()

    # 4.1 Basic ASCII tree
    rc, out, err = dz("tree")
    has_dz_header = "dz" in out.lower() and "dazzlecmd" in out.lower()
    # Check for Unicode box chars (should NOT be present)
    unicode_box = any(c in out for c in ['\u251c', '\u2514', '\u2502', '\u2500'])
    has_ascii = any(c in out for c in ['+', '|', '\\'])
    has_footer = "tool" in out.lower() and "kit" in out.lower()

    if has_dz_header and not unicode_box and has_ascii and has_footer:
        add_result("4.1", "Basic ASCII tree", "PASS",
                   stdout=out[:500], stderr=err)
    elif unicode_box:
        add_result("4.1", "Basic ASCII tree", "FAIL",
                   "Unicode box-drawing characters found!", stdout=out[:500], stderr=err)
    else:
        add_result("4.1", "Basic ASCII tree", "REVIEW",
                   f"header={has_dz_header}, ascii={has_ascii}, footer={has_footer}",
                   stdout=out[:500], stderr=err)

    # 4.2 --json output is valid JSON
    rc, out, err = dz("tree", "--json")
    try:
        data = json.loads(out)
        has_keys = all(k in data for k in ["root", "kits"])
        if has_keys:
            # Check each kit has expected fields
            kits = data.get("kits", {})
            if isinstance(kits, dict) and len(kits) > 0:
                sample_kit = next(iter(kits.values()))
                kit_keys = ["tools", "is_aggregator", "always_active", "state"]
                has_kit_keys = all(k in sample_kit for k in kit_keys)
                if has_kit_keys:
                    add_result("4.2", "--json output is valid JSON", "PASS",
                               f"Keys present, {len(kits)} kits")
                else:
                    missing = [k for k in kit_keys if k not in sample_kit]
                    add_result("4.2", "--json output is valid JSON", "FAIL",
                               f"Kit missing keys: {missing}. Has: {list(sample_kit.keys())}")
            else:
                add_result("4.2", "--json output is valid JSON", "FAIL",
                           f"kits is not a dict or empty: {type(kits)}")
        else:
            missing = [k for k in ["root", "kits"] if k not in data]
            add_result("4.2", "--json output is valid JSON", "FAIL",
                       f"Missing root keys: {missing}. Has: {list(data.keys())}")
    except json.JSONDecodeError as e:
        add_result("4.2", "--json output is valid JSON", "FAIL",
                   f"JSON parse error: {e}", stdout=out[:300], stderr=err)

    # 4.3 --depth 1 hides tools
    rc, out, err = dz("tree", "--depth", "1")
    # Should show kit names but no tool entries (no FQCN like core:fixpath)
    lines = out.strip().split('\n')
    # Look for FQCN patterns (kit:tool) in the body (not header/footer)
    import re
    fqcn_pattern = re.compile(r'\w+:\w+')
    # The tree should still have a footer with tool count
    has_footer = bool(re.search(r'\d+\s+tool', out.lower()))
    # Check that no tool detail lines appear (lines with descriptions after FQCN)
    # In depth 1, only kit-level entries should show
    # A heuristic: tools typically show as "tool_name  description"
    # Actually let's check: in full tree, tools have " -- " descriptions
    tool_lines = [l for l in lines if " -- " in l and not l.strip().startswith("dz")]
    if has_footer and len(tool_lines) == 0:
        add_result("4.3", "--depth 1 hides tools", "PASS",
                   stdout=out[:300], stderr=err)
    elif has_footer:
        add_result("4.3", "--depth 1 hides tools", "REVIEW",
                   f"Footer present but {len(tool_lines)} tool-like lines found",
                   stdout=out[:500], stderr=err)
    else:
        add_result("4.3", "--depth 1 hides tools", "FAIL",
                   f"No footer found", stdout=out[:300], stderr=err)

    # 4.4 --kit filter
    rc, out, err = dz("tree", "--kit", "core")
    out_lower = out.lower()
    if "core" in out_lower and "dazzletools" not in out_lower and "wtf" not in out_lower:
        add_result("4.4", "--kit filter (core only)", "PASS",
                   stdout=out[:300], stderr=err)
    elif "core" in out_lower:
        # dazzletools or wtf might appear as part of FQCN or header
        add_result("4.4", "--kit filter (core only)", "REVIEW",
                   "core present but other kit names also appear",
                   stdout=out[:500], stderr=err)
    else:
        add_result("4.4", "--kit filter (core only)", "FAIL",
                   "core not in output", stdout=out[:300], stderr=err)

    # 4.5 --kit with non-existent kit
    rc, out, err = dz("tree", "--kit", "ghost")
    combined = out + err
    if rc != 0 and ("not found" in combined.lower() or "error" in combined.lower()):
        add_result("4.5", "--kit with non-existent kit", "PASS",
                   stdout=out, stderr=err)
    elif rc != 0:
        add_result("4.5", "--kit with non-existent kit", "REVIEW",
                   f"Non-zero exit but unclear error message",
                   stdout=out, stderr=err)
    else:
        add_result("4.5", "--kit with non-existent kit", "FAIL",
                   f"Expected non-zero exit, got rc={rc}", stdout=out, stderr=err)

    # 4.6 --show-disabled
    reset()
    dz("kit", "disable", "dazzletools")
    rc1, out1, err1 = dz("tree")
    rc2, out2, err2 = dz("tree", "--show-disabled")

    # dazzletools should NOT be in first tree, SHOULD be in second
    dt_in_first = "dazzletools" in out1
    dt_in_second = "dazzletools" in out2
    disabled_marker = "disabled" in out2.lower()

    if not dt_in_first and dt_in_second and disabled_marker:
        add_result("4.6", "--show-disabled", "PASS",
                   stdout=out2[:300], stderr=err2)
    elif not dt_in_first and dt_in_second:
        add_result("4.6", "--show-disabled", "REVIEW",
                   "dazzletools appears in --show-disabled but no [disabled] marker",
                   stdout=out2[:300], stderr=err2)
    else:
        add_result("4.6", "--show-disabled", "FAIL",
                   f"dt_in_first={dt_in_first}, dt_in_second={dt_in_second}",
                   stdout=out2[:300], stderr=err2)

    # Cleanup
    dz("kit", "enable", "dazzletools")


# ============================================================
# SECTION 5: Favorites
# ============================================================
def run_section_5():
    print("\n=== SECTION 5: Favorites ===")
    reset()

    # 5.1 Set a favorite
    rc, out, err = dz("kit", "favorite", "testname", "core:fixpath")
    cfg = read_config()
    if "Favorite set: testname -> core:fixpath" in out:
        if cfg and cfg.get("favorites", {}).get("testname") == "core:fixpath":
            add_result("5.1", "Set a favorite", "PASS",
                       stdout=out, stderr=err)
        else:
            add_result("5.1", "Set a favorite", "FAIL",
                       f"Output ok but config wrong: {cfg}",
                       stdout=out, stderr=err)
    else:
        add_result("5.1", "Set a favorite", "FAIL",
                   f"Expected 'Favorite set' message", stdout=out, stderr=err)

    # 5.2 Reject reserved command names
    rc, out, err = dz("kit", "favorite", "list", "core:fixpath")
    combined = out + err
    if rc != 0 and "reserved" in combined.lower():
        add_result("5.2", "Reject reserved command names", "PASS",
                   stdout=out, stderr=err)
    else:
        add_result("5.2", "Reject reserved command names", "FAIL",
                   f"rc={rc}, expected non-zero with 'reserved' message",
                   stdout=out, stderr=err)

    # 5.3 Stale favorite target warns but saves
    rc, out, err = dz("kit", "favorite", "ghost", "ghost:nonexistent")
    combined = out + err
    has_warning = "warning" in combined.lower() or "not found" in combined.lower()
    has_set = "Favorite set: ghost -> ghost:nonexistent" in out
    if rc == 0 and has_set:
        cfg = read_config()
        if cfg and cfg.get("favorites", {}).get("ghost") == "ghost:nonexistent":
            if has_warning:
                add_result("5.3", "Stale favorite warns but saves", "PASS",
                           stdout=out, stderr=err)
            else:
                add_result("5.3", "Stale favorite warns but saves", "REVIEW",
                           "Saved ok but no warning about stale target",
                           stdout=out, stderr=err)
        else:
            add_result("5.3", "Stale favorite warns but saves", "FAIL",
                       f"Not saved in config: {cfg}", stdout=out, stderr=err)
    else:
        add_result("5.3", "Stale favorite warns but saves", "FAIL",
                   f"rc={rc}, has_set={has_set}", stdout=out, stderr=err)

    # 5.4 Unfavorite
    rc, out, err = dz("kit", "unfavorite", "testname")
    if "Favorite removed: testname" in out:
        cfg = read_config()
        if cfg and "testname" not in cfg.get("favorites", {}):
            add_result("5.4", "Unfavorite", "PASS",
                       stdout=out, stderr=err)
        else:
            add_result("5.4", "Unfavorite", "FAIL",
                       f"Message ok but testname still in config: {cfg}",
                       stdout=out, stderr=err)
    else:
        add_result("5.4", "Unfavorite", "FAIL",
                   f"Expected 'Favorite removed' message", stdout=out, stderr=err)

    # 5.5 Unfavorite non-existent key
    rc, out, err = dz("kit", "unfavorite", "does-not-exist")
    if rc == 0 and "no favorite" in out.lower():
        add_result("5.5", "Unfavorite non-existent key", "PASS",
                   stdout=out, stderr=err)
    elif rc == 0:
        add_result("5.5", "Unfavorite non-existent key", "REVIEW",
                   f"Exit 0 but message doesn't match expected",
                   stdout=out, stderr=err)
    else:
        add_result("5.5", "Unfavorite non-existent key", "FAIL",
                   f"rc={rc}", stdout=out, stderr=err)


# ============================================================
# SECTION 6: Silencing and shadowing
# ============================================================
def run_section_6():
    print("\n=== SECTION 6: Silencing and shadowing ===")
    reset()

    # 6.1 Silence a deep tool
    rc, out, err = dz("kit", "silence", "wtf:core:restarted")
    combined = out + err
    if "silenced" in combined.lower() and "wtf:core:restarted" in combined.lower():
        cfg = read_config()
        silenced = cfg.get("silenced_hints", {}).get("tools", []) if cfg else []
        if "wtf:core:restarted" in silenced:
            add_result("6.1", "Silence a deep tool", "PASS",
                       stdout=out, stderr=err)
        else:
            add_result("6.1", "Silence a deep tool", "FAIL",
                       f"Not in config silenced_hints.tools: {cfg}",
                       stdout=out, stderr=err)
    else:
        add_result("6.1", "Silence a deep tool", "FAIL",
                   f"No 'silenced' message", stdout=out, stderr=err)

    # 6.2 Idempotent silence (no duplicates)
    dz("kit", "silence", "wtf:core:restarted")
    dz("kit", "silence", "wtf:core:restarted")
    cfg = read_config()
    silenced = cfg.get("silenced_hints", {}).get("tools", []) if cfg else []
    count = silenced.count("wtf:core:restarted")
    if count == 1:
        add_result("6.2", "Idempotent silence (no duplicates)", "PASS",
                   f"Appears {count} time(s)")
    else:
        add_result("6.2", "Idempotent silence (no duplicates)", "FAIL",
                   f"Appears {count} time(s) in: {silenced}")

    # 6.3 Shadow a tool and verify it disappears
    reset()
    rc1, out1, err1 = dz("list")
    safedel_before = "safedel" in out1.lower()

    dz("kit", "shadow", "core:safedel")
    rc2, out2, err2 = dz("list")
    safedel_after = "safedel" in out2.lower()

    if safedel_before and not safedel_after:
        # Also test that dz safedel --help fails
        rc3, out3, err3 = dz("safedel", "--help")
        combined3 = out3 + err3
        if rc3 != 0 or "invalid choice" in combined3.lower() or "error" in combined3.lower():
            add_result("6.3", "Shadow a tool (disappears from list+dispatch)", "PASS",
                       stdout=out2[:200], stderr=err2)
        else:
            add_result("6.3", "Shadow a tool (disappears from list+dispatch)", "REVIEW",
                       "Disappeared from list but safedel --help still works?",
                       stdout=out3, stderr=err3)
    elif not safedel_before:
        add_result("6.3", "Shadow a tool (disappears from list+dispatch)", "SKIP",
                   "safedel not visible before shadowing -- can't test")
    else:
        add_result("6.3", "Shadow a tool (disappears from list+dispatch)", "FAIL",
                   f"safedel still visible after shadow", stdout=out2[:200], stderr=err2)

    # Cleanup: unshadow
    dz("kit", "unshadow", "core:safedel")

    # 6.4 dz kit silenced shows all three
    reset()
    dz("kit", "favorite", "foo", "core:fixpath")
    dz("kit", "silence", "wtf:core:locked")
    dz("kit", "shadow", "core:safedel")
    rc, out, err = dz("kit", "silenced")

    combined = out + err
    has_silenced = "silenced" in combined.lower()
    has_shadowed = "shadow" in combined.lower()
    has_favorites = "favorite" in combined.lower()
    has_locked = "wtf:core:locked" in combined
    has_safedel = "core:safedel" in combined
    has_foo = "foo" in combined

    if has_silenced and has_shadowed and has_favorites and has_locked and has_safedel and has_foo:
        add_result("6.4", "dz kit silenced shows all three", "PASS",
                   stdout=out, stderr=err)
    else:
        add_result("6.4", "dz kit silenced shows all three", "REVIEW",
                   f"silenced={has_silenced}, shadowed={has_shadowed}, favorites={has_favorites}, "
                   f"locked={has_locked}, safedel={has_safedel}, foo={has_foo}",
                   stdout=out, stderr=err)

    # Cleanup
    dz("kit", "unshadow", "core:safedel")

    # 6.5 Shadowing frees the short name (manual)
    add_result("6.5", "Shadowing frees the short name (collision test)", "MANUAL",
               "Requires two kits with same short-name tool to test collision resolution")


# ============================================================
# SECTION 7: dz kit list readability
# ============================================================
def run_section_7():
    print("\n=== SECTION 7: dz kit list readability ===")
    reset()

    # 7.1 Blank-line separators
    rc, out, err = dz("kit", "list")
    # Check for blank lines between kit blocks
    has_blank_sep = "\n\n" in out
    if has_blank_sep:
        add_result("7.1", "Blank-line separators between kits", "PASS",
                   stdout=out[:500], stderr=err)
    else:
        add_result("7.1", "Blank-line separators between kits", "REVIEW",
                   "No blank line separators found - check readability",
                   stdout=out[:500], stderr=err)

    # 7.2 Kit-specific listing
    rc, out, err = dz("kit", "list", "core")
    out_lower = out.lower()
    has_header = "kit:" in out_lower or "core" in out_lower
    has_tools = "tool" in out_lower
    has_always = "always" in out_lower

    if has_header and has_tools:
        add_result("7.2", "Kit-specific listing (core)", "PASS",
                   stdout=out[:500], stderr=err)
    else:
        add_result("7.2", "Kit-specific listing (core)", "REVIEW",
                   f"header={has_header}, tools={has_tools}, always={has_always}",
                   stdout=out[:500], stderr=err)


# ============================================================
# SECTION 8: dz kit add (git submodule)
# ============================================================
def run_section_8():
    print("\n=== SECTION 8: dz kit add (git submodule) ===")

    # 8.1 Dry-run: verify error on duplicate
    rc, out, err = dz("kit", "add", "https://github.com/DazzleTools/dazzlecmd.git", "--name", "core")
    combined = out + err
    if rc != 0 and ("already exists" in combined.lower() or "error" in combined.lower()):
        add_result("8.1", "Error on duplicate kit name", "PASS",
                   stdout=out, stderr=err)
    elif rc != 0:
        add_result("8.1", "Error on duplicate kit name", "REVIEW",
                   f"Non-zero exit but message unclear", stdout=out, stderr=err)
    else:
        add_result("8.1", "Error on duplicate kit name", "FAIL",
                   f"Expected error, got rc=0", stdout=out, stderr=err)

    # 8.2 and 8.3 require real git operations
    add_result("8.2", "Derive name from URL", "MANUAL",
               "Requires a real git submodule add to a throwaway repo")
    add_result("8.3", "Invalid URL fails gracefully", "MANUAL",
               "Requires real git submodule add with invalid URL")


# ============================================================
# SECTION 9: Integration with existing features
# ============================================================
def run_section_9():
    print("\n=== SECTION 9: Integration with existing features ===")
    reset()

    # 9.1 Phase 2 FQCN dispatch still works
    rc1, out1, err1 = dz("locked", "--help")
    rc2, out2, err2 = dz("wtf:core:locked", "--help")
    combined1 = out1 + err1
    combined2 = out2 + err2

    # Both should succeed and show help for the locked tool
    if rc1 == 0 and rc2 == 0:
        add_result("9.1", "Phase 2 FQCN dispatch still works", "PASS",
                   f"Both short-name and FQCN dispatch work", stdout=out1[:200])
    elif rc1 == 0 or rc2 == 0:
        add_result("9.1", "Phase 2 FQCN dispatch still works", "FAIL",
                   f"short-name rc={rc1}, FQCN rc={rc2}",
                   stdout=out1[:200] + "\n---\n" + out2[:200],
                   stderr=err1 + "\n---\n" + err2)
    else:
        add_result("9.1", "Phase 2 FQCN dispatch still works", "FAIL",
                   f"Both failed: rc1={rc1}, rc2={rc2}",
                   stdout=combined1[:200], stderr=combined2[:200])

    # 9.2 Phase 2 recursive discovery still works
    rc, out, err = dz("list")
    import re
    match = re.search(r'(\d+)\s+tool\(s\)', out)
    n = int(match.group(1)) if match else 0
    if n > 0:
        add_result("9.2", "Phase 2 recursive discovery (tool count)", "PASS",
                   f"{n} tools found")
    else:
        add_result("9.2", "Phase 2 recursive discovery (tool count)", "FAIL",
                   f"No tools found or footer missing", stdout=out, stderr=err)

    # 9.3 Rerooting hint
    add_result("9.3", "Rerooting hint fires (deep FQCN fixture)", "SKIP",
               "Requires deeply-nested fixture to construct")

    # 9.4 dz --version reports 0.7.11
    rc, out, err = dz("--version")
    combined = out + err
    if "0.7.11" in combined:
        add_result("9.4", "dz --version reports 0.7.11", "PASS",
                   stdout=out, stderr=err)
    else:
        add_result("9.4", "dz --version reports 0.7.11", "FAIL",
                   f"0.7.11 not found in output", stdout=out, stderr=err)


# ============================================================
# SECTION 10: Cleanup
# ============================================================
def run_section_10():
    print("\n=== SECTION 10: Cleanup ===")

    # 10.1-10.3: Clean up temp files
    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)
        add_result("10.1-3", "Cleanup temp config file", "PASS",
                   f"Deleted {CONFIG_PATH}")
    else:
        add_result("10.1-3", "Cleanup temp config file", "PASS",
                   f"Already clean")

    tree_json = os.path.join(tempfile.gettempdir(), "dz-tree.json")
    if os.path.exists(tree_json):
        os.remove(tree_json)

    # 10.4 Verify dz list works without isolation
    # We can't really unset our env var in-process in a meaningful way for subprocess,
    # but we can verify no temp files remain
    add_result("10.4", "Verify normal state restored", "MANUAL",
               "Human should verify dz list shows normal tools after unsetting DAZZLECMD_CONFIG")


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"Phase 3 Checklist Test Runner")
    print(f"Config isolation: {CONFIG_PATH}")
    print(f"Working dir: {CWD}")
    print(f"Python: {PYTHON}")
    print(f"=" * 60)

    try:
        run_section_1()
        run_section_2()
        run_section_3()
        run_section_4()
        run_section_5()
        run_section_6()
        run_section_7()
        run_section_8()
        run_section_9()
        run_section_10()
    except Exception as e:
        print(f"\nFATAL ERROR during test execution: {e}")
        traceback.print_exc()
        results.append(TestResult("FATAL", str(e), "FAIL", traceback.format_exc()))

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")

    counts = {"PASS": 0, "FAIL": 0, "REVIEW": 0, "MANUAL": 0, "SKIP": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    for status, count in counts.items():
        print(f"  {status}: {count}")
    print(f"  TOTAL: {len(results)}")

    # Write detailed report
    report_path = r"C:\code\dazzlecmd\github\private\claude\2026-04-13__tester-agent-report_phase3-checklist.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Phase 3 Test Checklist Report\n\n")
        f.write(f"**Date**: 2026-04-13\n")
        f.write(f"**Checklist**: v0.7.11__Phase3__kit-management-and-config-write.md\n")
        f.write(f"**Config isolation**: `{CONFIG_PATH}`\n")
        f.write(f"**Runner**: `tests/one-offs/run_phase3_checklist.py`\n\n")

        f.write("## Summary\n\n")
        f.write("| Status | Count |\n|--------|-------|\n")
        for status, count in counts.items():
            f.write(f"| {status} | {count} |\n")
        f.write(f"| **TOTAL** | **{len(results)}** |\n\n")

        f.write("## Detailed Results\n\n")
        for r in results:
            symbol = {"PASS": "[OK]", "FAIL": "[FAIL]", "REVIEW": "[REVIEW]",
                      "MANUAL": "[MANUAL]", "SKIP": "[SKIP]"}.get(r.status, "???")
            f.write(f"### {r.test_id} -- {r.description} {symbol}\n\n")
            f.write(f"**Status**: {r.status}\n\n")
            if r.details:
                f.write(f"**Details**: {r.details}\n\n")
            if r.stdout:
                f.write(f"<details><summary>stdout</summary>\n\n```\n{r.stdout[:1000]}\n```\n\n</details>\n\n")
            if r.stderr:
                f.write(f"<details><summary>stderr</summary>\n\n```\n{r.stderr[:1000]}\n```\n\n</details>\n\n")

        f.write("## Edge Cases Discovered\n\n")
        f.write("(See REVIEW and FAIL items above for any unexpected behaviors.)\n\n")

        f.write("## Recommendations for Additional Automated Tests\n\n")
        fail_items = [r for r in results if r.status == "FAIL"]
        review_items = [r for r in results if r.status == "REVIEW"]
        if fail_items:
            f.write("### Failures requiring investigation\n\n")
            for r in fail_items:
                f.write(f"- **{r.test_id}**: {r.description} -- {r.details}\n")
            f.write("\n")
        if review_items:
            f.write("### Items needing human review\n\n")
            for r in review_items:
                f.write(f"- **{r.test_id}**: {r.description} -- {r.details}\n")
            f.write("\n")

    print(f"\nDetailed report written to: {report_path}")
    return 1 if counts["FAIL"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
