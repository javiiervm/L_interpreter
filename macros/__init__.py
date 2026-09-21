"""Auto-discovered source-level macros for language L.

Drop a new ``.py`` file in this package and register a macro with ``@macro``.
Macro modules are discovered automatically when the package is imported.
"""

from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules

from .registry import (
    IDENTIFIER_PATTERN,
    MACROS,
    MacroExpansionContext,
    MacroExpansionError,
    macro,
)

_INTERNAL_MODULES = {"registry"}


def _load_macro_modules() -> None:
    module_names = sorted(
        module_info.name
        for module_info in iter_modules(__path__)
        if not module_info.ispkg
        and not module_info.name.startswith("_")
        and module_info.name not in _INTERNAL_MODULES
    )
    for module_name in module_names:
        import_module(f"{__name__}.{module_name}")


_load_macro_modules()

__all__ = [
    "IDENTIFIER_PATTERN",
    "MACROS",
    "MacroExpansionContext",
    "MacroExpansionError",
    "macro",
]
