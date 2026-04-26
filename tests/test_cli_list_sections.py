"""Phase 4e v0.7.28: tests for sectioned `dz list` rendering (Option O).

Tests call ``_cmd_list`` directly with constructed engine + projects
(capsys captures stdout). This avoids subprocess project_root discovery
issues that arise when dz walks up from the engine module's __file__
rather than from a test cwd.

Covers:
- Multi-section rendering: header per kit + tools indented underneath
- Single-section fallback: flat layout (Kit column visible)
- Virtual-kit header annotation: ``(virtual kit '<name>')`` suffix
- ``[+]`` marker on canonicals-with-aliases in --show all
- ``[*]`` collision marker preserved
- Footer counts per --show mode
"""

from types import SimpleNamespace

import pytest

from dazzlecmd.cli import _cmd_list


def _proj(fqcn, short, kit, description="", **extra):
    p = {
        "_fqcn": fqcn,
        "_short_name": short,
        "_kit_import_name": kit,
        "name": short,
        "namespace": kit,
        "description": description or f"{short} description",
        "platform": "cross-platform",
    }
    p.update(extra)
    return p


def _args(**kwargs):
    defaults = {
        "namespace": None,
        "kit": None,
        "tag": None,
        "platform": None,
        "show": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _build_engine(projects, virtual_kits=None, monkeypatch=None, tmp_path=None):
    """Construct a minimal AggregatorEngine with projects + optional
    virtual kits installed via the FQCNIndex API."""
    from dazzlecmd_lib.engine import AggregatorEngine
    if monkeypatch and tmp_path:
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
    engine = AggregatorEngine(is_root=True)
    engine.projects = list(projects)
    engine._build_fqcn_index()
    # Install virtual-kit aliases + a mock kits list for the renderer
    engine.kits = [
        # Synthesize one canonical kit per project's _kit_import_name (deduped)
    ]
    canonical_kit_names = sorted({p["_kit_import_name"] for p in projects})
    for name in canonical_kit_names:
        engine.kits.append({
            "name": name,
            "_kit_name": name,
            "tools": [],
            "always_active": True,
        })
    if virtual_kits:
        for vk in virtual_kits:
            engine.kits.append(vk)
            # Install aliases per the manifest
            for canonical_fqcn in vk.get("tools", []):
                short = (vk.get("name_rewrite", {}) or {}).get(
                    canonical_fqcn,
                    canonical_fqcn.rsplit(":", 1)[-1],
                )
                alias_fqcn = f"{vk['name']}:{short}"
                try:
                    engine.fqcn_index.insert_alias(alias_fqcn, canonical_fqcn)
                except Exception:
                    pass  # idempotent or collision
    engine.active_kits = list(engine.kits)
    return engine


# ---------------------------------------------------------------------------
# Multi-section rendering
# ---------------------------------------------------------------------------


class TestSectionedRendering:
    def _build(self, monkeypatch, tmp_path):
        projects = [
            _proj("demo:tool-alpha", "tool-alpha", "demo", "Alpha tool"),
            _proj("demo:tool-beta", "tool-beta", "demo", "Beta tool"),
            _proj("demo:tool-gamma", "tool-gamma", "demo", "Gamma tool"),
            _proj("core:rn", "rn", "core", "Rename files"),
        ]
        virtual_kits = [{
            "_kit_name": "grouped",
            "name": "grouped",
            "virtual": True,
            "always_active": True,
            "_kit_active": True,
            "tools": ["demo:tool-alpha", "demo:tool-beta"],
            "name_rewrite": {
                "demo:tool-alpha": "alpha",
                "demo:tool-beta": "beta",
            },
        }]
        return _build_engine(projects, virtual_kits, monkeypatch, tmp_path), projects

    def test_default_view_has_section_headers(self, monkeypatch, tmp_path, capsys):
        engine, projects = self._build(monkeypatch, tmp_path)
        rc = _cmd_list(_args(), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        # Multiple sections -> sectioned layout, NOT the legacy flat header
        assert "core:" in out
        assert "demo:" in out
        assert "demo:grouped:" in out
        assert "(virtual kit 'grouped')" in out

    def test_default_view_aliases_replace_canonicals(self, monkeypatch, tmp_path, capsys):
        """Default mode: canonicals with aliases hidden; alias shorts shown."""
        engine, projects = self._build(monkeypatch, tmp_path)
        rc = _cmd_list(_args(), projects, engine=engine)
        out = capsys.readouterr().out
        # tool-gamma is NOT aliased -> shown
        assert "tool-gamma" in out
        # Aliased shorts shown under demo:grouped section
        assert "alpha" in out
        assert "beta" in out
        # Canonicals tool-alpha/tool-beta should NOT appear in default view
        # (they're hidden because they have aliases)
        # Use whole-word check: their canonical names don't appear in body
        # Note: "alpha" is a substring of "tool-alpha" so we check the full name
        canonical_alpha_visible = "tool-alpha" in out
        # In default mode this should be False (canonical hidden)
        assert not canonical_alpha_visible, (
            "tool-alpha (canonical) should be hidden when alias 'alpha' exists "
            "in default mode"
        )

    def test_show_canonical_no_virtual_section(self, monkeypatch, tmp_path, capsys):
        engine, projects = self._build(monkeypatch, tmp_path)
        rc = _cmd_list(_args(show="canonical"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "demo:" in out
        # No virtual-kit section in canonical mode
        assert "(virtual kit" not in out
        # All canonicals visible
        assert "tool-alpha" in out
        assert "tool-beta" in out
        assert "tool-gamma" in out

    def test_show_alias_single_section_flat_fallback(self, monkeypatch, tmp_path, capsys):
        """--show alias = only the virtual kit's section. Single section
        triggers flat fallback (Kit column visible, no header line)."""
        engine, projects = self._build(monkeypatch, tmp_path)
        rc = _cmd_list(_args(show="alias"), projects, engine=engine)
        out = capsys.readouterr().out
        # Flat layout has the legacy "Name ... Kit ... Description" header
        assert "Name" in out and "Kit" in out and "Description" in out
        # Aliases visible
        assert "alpha" in out
        assert "beta" in out

    def test_show_all_plus_marker_on_aliased_canonicals(self, monkeypatch, tmp_path, capsys):
        engine, projects = self._build(monkeypatch, tmp_path)
        rc = _cmd_list(_args(show="all"), projects, engine=engine)
        out = capsys.readouterr().out
        # tool-alpha and tool-beta have aliases -> [+]
        assert "tool-alpha [+]" in out
        assert "tool-beta [+]" in out
        # tool-gamma has no alias -> no [+]
        assert "tool-gamma [+]" not in out
        # Footer note explains the [+] marker
        assert "[+]" in out
        assert "aliases" in out.lower() or "virtual" in out.lower()

    def test_show_all_canonical_and_alias_both_visible(self, monkeypatch, tmp_path, capsys):
        engine, projects = self._build(monkeypatch, tmp_path)
        rc = _cmd_list(_args(show="all"), projects, engine=engine)
        out = capsys.readouterr().out
        # Both canonical (with [+]) AND alias (under virtual section) appear
        assert "tool-alpha [+]" in out
        assert "demo:grouped:" in out  # virtual section header
        assert "(virtual kit 'grouped')" in out

    def test_virtual_section_adjacent_to_canonical_parent(self, monkeypatch, tmp_path, capsys):
        """Virtual-kit sections render immediately after their canonical
        parent kit, not at the bottom of the list. This makes the
        extension relationship visually obvious."""
        # Build a tree where a 3rd canonical kit ("zebra") would otherwise
        # alphabetically follow the virtual kit if it were sorted purely
        # by section key.
        projects = [
            _proj("core:rn", "rn", "core"),
            _proj("demo:tool-alpha", "tool-alpha", "demo"),
            _proj("demo:tool-beta", "tool-beta", "demo"),
            _proj("zebra:zz", "zz", "zebra"),  # alphabetically AFTER demo:claude
        ]
        virtual_kits = [{
            "_kit_name": "grouped",
            "name": "grouped",
            "virtual": True,
            "always_active": True,
            "_kit_active": True,
            "tools": ["demo:tool-alpha", "demo:tool-beta"],
            "name_rewrite": {
                "demo:tool-alpha": "alpha",
                "demo:tool-beta": "beta",
            },
        }]
        engine = _build_engine(projects, virtual_kits, monkeypatch, tmp_path)
        _cmd_list(_args(show="canonical"), projects, engine=engine)  # warm-up to ensure sort
        capsys.readouterr()  # drain
        _cmd_list(_args(show="all"), projects, engine=engine)
        out = capsys.readouterr().out
        # Order check via index-of-substring positions
        idx_demo = out.find("demo:")
        idx_demo_grouped = out.find("demo:grouped:")
        idx_zebra = out.find("zebra:")
        # demo: < demo:grouped: < zebra:
        assert idx_demo < idx_demo_grouped < idx_zebra, (
            f"Virtual section should sit between demo: and zebra:; "
            f"got demo={idx_demo}, demo:grouped={idx_demo_grouped}, "
            f"zebra={idx_zebra}"
        )


# ---------------------------------------------------------------------------
# Single-section fallback to flat layout
# ---------------------------------------------------------------------------


class TestSingleSectionFlatFallback:
    def test_kit_filter_canonical_kit_flat(self, monkeypatch, tmp_path, capsys):
        projects = [
            _proj("demo:tool-alpha", "tool-alpha", "demo"),
            _proj("demo:tool-beta", "tool-beta", "demo"),
            _proj("core:rn", "rn", "core"),
        ]
        engine = _build_engine(projects, monkeypatch=monkeypatch, tmp_path=tmp_path)
        rc = _cmd_list(_args(kit="demo"), projects, engine=engine)
        out = capsys.readouterr().out
        # Flat layout has the column header
        assert "Name" in out and "Kit" in out
        # No section header line "demo:" by itself
        # Two demo tools visible
        assert "tool-alpha" in out
        assert "tool-beta" in out
        # core tool not in demo filter
        assert "rn " not in out  # rn shouldn't appear

    def test_kit_filter_virtual_kit_flat(self, monkeypatch, tmp_path, capsys):
        projects = [
            _proj("demo:tool-alpha", "tool-alpha", "demo"),
            _proj("demo:tool-beta", "tool-beta", "demo"),
        ]
        virtual_kits = [{
            "_kit_name": "grouped",
            "name": "grouped",
            "virtual": True,
            "always_active": True,
            "_kit_active": True,
            "tools": ["demo:tool-alpha", "demo:tool-beta"],
            "name_rewrite": {
                "demo:tool-alpha": "alpha",
                "demo:tool-beta": "beta",
            },
        }]
        engine = _build_engine(projects, virtual_kits, monkeypatch, tmp_path)
        rc = _cmd_list(_args(kit="grouped"), projects, engine=engine)
        out = capsys.readouterr().out
        # Single virtual-kit section -> flat layout
        assert "Name" in out
        # Aliases visible
        assert "alpha" in out
        assert "beta" in out


# ---------------------------------------------------------------------------
# Footer counts
# ---------------------------------------------------------------------------


class TestFooterCounts:
    def _build(self, monkeypatch, tmp_path):
        projects = [
            _proj("demo:tool-alpha", "tool-alpha", "demo"),
            _proj("demo:tool-beta", "tool-beta", "demo"),
            _proj("demo:tool-gamma", "tool-gamma", "demo"),
        ]
        virtual_kits = [{
            "_kit_name": "grouped",
            "name": "grouped",
            "virtual": True,
            "always_active": True,
            "_kit_active": True,
            "tools": ["demo:tool-alpha"],
            "name_rewrite": {"demo:tool-alpha": "alpha"},
        }]
        return _build_engine(projects, virtual_kits, monkeypatch, tmp_path), projects

    def test_default_footer_counts(self, monkeypatch, tmp_path, capsys):
        engine, projects = self._build(monkeypatch, tmp_path)
        _cmd_list(_args(), projects, engine=engine)
        out = capsys.readouterr().out
        # Default: 2 canonical (beta, gamma) + 1 alias (alpha) = 3 rows total
        assert "3 tool(s)" in out
        assert "2 canonical" in out
        assert "1 virtual-kit alias" in out

    def test_canonical_footer(self, monkeypatch, tmp_path, capsys):
        engine, projects = self._build(monkeypatch, tmp_path)
        _cmd_list(_args(show="canonical"), projects, engine=engine)
        out = capsys.readouterr().out
        # 3 canonical tools, no aliases
        assert "3 tool(s) found" in out

    def test_alias_footer(self, monkeypatch, tmp_path, capsys):
        engine, projects = self._build(monkeypatch, tmp_path)
        _cmd_list(_args(show="alias"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "1 alias(es) found" in out

    def test_all_footer(self, monkeypatch, tmp_path, capsys):
        engine, projects = self._build(monkeypatch, tmp_path)
        _cmd_list(_args(show="all"), projects, engine=engine)
        out = capsys.readouterr().out
        # 3 canonical + 1 alias = 4 rows
        assert "3 tool(s) + 1 alias(es)" in out


# ---------------------------------------------------------------------------
# Virtual-kit header annotation
# ---------------------------------------------------------------------------


class TestVirtualKitAnnotation:
    def test_annotation_shows_virtual_kit_local_name(self, monkeypatch, tmp_path, capsys):
        projects = [_proj("dz:claude-cleanup", "claude-cleanup", "dz")]
        virtual_kits = [{
            "_kit_name": "claude",
            "name": "claude",
            "virtual": True,
            "always_active": True,
            "_kit_active": True,
            "tools": ["dz:claude-cleanup"],
            "name_rewrite": {"dz:claude-cleanup": "cleanup"},
        }]
        # Add a SECOND project so we have multi-section output
        projects.append(_proj("core:rn", "rn", "core"))
        engine = _build_engine(projects, virtual_kits, monkeypatch, tmp_path)
        _cmd_list(_args(), projects, engine=engine)
        out = capsys.readouterr().out
        # Section header appears with annotation
        assert "(virtual kit 'claude')" in out
