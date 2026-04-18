"""Per-engine meta-command registry for dazzlecmd-pattern aggregators.

A **meta-command** is an aggregator-level CLI subcommand that isn't a
discovered tool (e.g., ``list``, ``info``, ``kit``, ``version`` —
orthogonal to the tools the aggregator dispatches).

Each ``AggregatorEngine`` owns a ``MetaCommandRegistry`` instance.
Library defaults auto-register at engine construction (opt-out via
``include_default_meta_commands=False``). Downstream aggregators can
``register()`` new commands, ``override()`` defaults, or ``unregister()``
commands they don't want.

Unlike ``RunnerRegistry`` (global singleton for runtime types), this
registry is **per-engine instance** — two aggregators in the same Python
process have independent registries. That's essential for wtf-windows
running standalone vs. dazzlecmd running with wtf embedded as a kit.

Lifecycle: the registry is mutable until ``engine.run()`` calls
``lock()``. After that, mutations raise ``RegistryLockedError`` until
the next run. This prevents subtle bugs where a late registration
modifies the registry after the argparse parser has already been built.

Example::

    engine = AggregatorEngine(...)  # defaults auto-registered
    engine.meta_registry.register("mode", mode_parser, mode_handler)
    engine.meta_registry.override("list", handler=custom_list_handler)
    engine.meta_registry.unregister("tree")
    engine.run()
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional


class RegistryLockedError(RuntimeError):
    """Raised when the registry is mutated after ``lock()`` was called.

    The registry locks when the engine begins dispatching (inside
    ``engine.run()``). Registration must happen beforehand — typically
    in the aggregator's ``main()`` between construction and ``run()``.
    """


class MetaCommandAlreadyRegisteredError(KeyError):
    """Raised by ``register()`` when the name is already registered.

    Use ``override()`` to replace an existing registration, or
    ``unregister()`` first if you want to change the semantics.
    """


class MetaCommandNotRegisteredError(KeyError):
    """Raised by ``override()`` / ``unregister()`` for an unknown name."""


class MetaCommandRegistry:
    """Per-engine registry of meta-commands.

    A meta-command entry is a ``(parser_factory, handler)`` tuple:

    - ``parser_factory(subparsers)``: adds an argparse subparser to the
      given ``subparsers`` action. Responsible for calling
      ``add_parser(name, ...)`` and ``set_defaults(_meta=<tag>)``.
    - ``handler(args, engine, projects, kits, project_root)``: executes
      the command. Returns an int exit code.

    The parser_factory and handler signatures are stable across library
    versions. Library-provided default factories and handlers are also
    importable from ``dazzlecmd_lib.default_meta_commands``.
    """

    def __init__(self):
        self._commands: dict[str, tuple[Callable, Callable]] = {}
        self._locked = False

    def register(
        self,
        name: str,
        parser_factory: Callable,
        handler: Callable,
    ) -> None:
        """Add a new meta-command.

        Raises:
            MetaCommandAlreadyRegisteredError: if ``name`` is already
                registered. Use ``override()`` to replace.
            RegistryLockedError: if the registry is locked.
        """
        self._check_not_locked()
        if name in self._commands:
            raise MetaCommandAlreadyRegisteredError(
                f"Meta-command {name!r} is already registered. "
                f"Use override() to replace, or unregister() first."
            )
        self._commands[name] = (parser_factory, handler)

    def override(
        self,
        name: str,
        parser_factory: Optional[Callable] = None,
        handler: Optional[Callable] = None,
        *,
        parser: Optional[Callable] = None,
    ) -> None:
        """Replace an existing meta-command's parser, handler, or both.

        Keyword-only aliases: ``parser=`` is equivalent to
        ``parser_factory=`` (shorter form for the common override case).

        Pass only the parts you want to replace:

        - ``override("info", handler=my_handler)`` — keep stock parser,
          replace handler
        - ``override("list", parser=my_parser)`` — replace parser, keep
          stock handler
        - ``override("list", parser=p, handler=h)`` — replace both

        Raises:
            MetaCommandNotRegisteredError: if ``name`` isn't registered.
                Use ``register()`` for new commands.
            ValueError: if neither parser nor handler is provided.
            RegistryLockedError: if the registry is locked.
        """
        self._check_not_locked()
        if name not in self._commands:
            raise MetaCommandNotRegisteredError(
                f"Meta-command {name!r} is not registered. "
                f"Use register() to add it."
            )

        # Allow both ``parser_factory=`` and ``parser=`` spellings
        if parser_factory is None and parser is not None:
            parser_factory = parser
        if parser_factory is None and handler is None:
            raise ValueError(
                "override() requires at least one of parser_factory/parser "
                "or handler to be provided."
            )

        existing_parser, existing_handler = self._commands[name]
        new_parser = parser_factory if parser_factory is not None else existing_parser
        new_handler = handler if handler is not None else existing_handler
        self._commands[name] = (new_parser, new_handler)

    def unregister(self, name: str) -> None:
        """Remove a meta-command.

        After ``unregister("tree")`` the engine's ``reserved_commands``
        no longer contains "tree" either — aggregators can name a tool
        ``tree`` if the default is removed.

        Raises:
            MetaCommandNotRegisteredError: if ``name`` isn't registered.
            RegistryLockedError: if the registry is locked.
        """
        self._check_not_locked()
        if name not in self._commands:
            raise MetaCommandNotRegisteredError(
                f"Meta-command {name!r} is not registered."
            )
        del self._commands[name]

    def registered(self) -> list[str]:
        """Return the currently-registered meta-command names (sorted)."""
        return sorted(self._commands.keys())

    def resolve(self, name: str) -> Optional[tuple[Callable, Callable]]:
        """Return ``(parser_factory, handler)`` for ``name`` or ``None``."""
        return self._commands.get(name)

    def build_parsers(self, subparsers) -> None:
        """Invoke all registered parser factories against ``subparsers``.

        Called by the engine's parser_builder during ``run()``. After
        this returns, the argparse parser has one subparser per
        registered meta-command.
        """
        for name in self.registered():
            parser_factory, _ = self._commands[name]
            parser_factory(subparsers)

    def dispatch(self, args, engine, projects, kits, project_root) -> int:
        """Route an argparse result to the appropriate handler.

        Inspects ``args._meta`` (set by parser factories via
        ``set_defaults(_meta=<name>)``) and dispatches to the matching
        handler. Returns the handler's exit code, or 1 if no ``_meta``
        tag is set or no handler is registered.
        """
        meta = getattr(args, "_meta", None)
        if meta is None:
            return 1
        entry = self._commands.get(meta)
        if entry is None:
            return 1
        _, handler = entry
        return handler(args, engine, projects, kits, project_root)

    def lock(self) -> None:
        """Lock the registry. Subsequent mutations raise.

        Called by ``engine.run()`` before parser construction to prevent
        registrations from racing with dispatch. Call ``unlock()`` to
        re-enable mutations (rare — typically only in tests or repeated
        invocations).
        """
        self._locked = True

    def unlock(self) -> None:
        """Unlock a previously-locked registry (rare; typically test use)."""
        self._locked = False

    def is_locked(self) -> bool:
        """Return True if the registry is currently locked."""
        return self._locked

    def clear(self) -> None:
        """Remove all registrations. Usable in test setup for a clean slate.

        Raises ``RegistryLockedError`` if locked. Does not re-register
        defaults — call ``default_meta_commands.register_all(registry)``
        afterwards if you want them back.
        """
        self._check_not_locked()
        self._commands = {}

    def _check_not_locked(self) -> None:
        if self._locked:
            raise RegistryLockedError(
                "MetaCommandRegistry is locked; cannot modify after "
                "engine.run() has begun dispatch. Register meta-commands "
                "before calling engine.run()."
            )

    def __repr__(self) -> str:
        state = "locked" if self._locked else "mutable"
        names = ", ".join(self.registered()) or "(empty)"
        return f"MetaCommandRegistry({state}, [{names}])"

    def __contains__(self, name: str) -> bool:
        return name in self._commands

    def __len__(self) -> int:
        return len(self._commands)
