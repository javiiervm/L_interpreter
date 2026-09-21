"""Shared infrastructure for source-level L macros."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Match, Optional, Pattern, Sequence


IDENTIFIER_PATTERN = r"[A-Za-z][A-Za-z0-9_]*"
_VARIABLE_SCAN_RE = re.compile(r"\b(?:Y|X\d*|Z\d*)\b", re.IGNORECASE)
_LABEL_SCAN_RE = re.compile(r"\(\s*([A-Za-z][A-Za-z0-9_]*)\s*\)")


class MacroExpansionError(ValueError):
    """Raised when a macro cannot be expanded safely."""


@dataclass
class MacroExpansionContext:
    """Allocator for names introduced by macro expansions."""

    used_variables: set[str] = field(default_factory=set)
    used_labels: set[str] = field(default_factory=set)
    next_variable_index: int = 1
    next_label_index: int = 1

    @classmethod
    def from_source(cls, text: str) -> "MacroExpansionContext":
        variables = {match.group(0).upper() for match in _VARIABLE_SCAN_RE.finditer(text)}
        labels = {match.group(1).upper() for match in _LABEL_SCAN_RE.finditer(text)}

        if "X" in variables:
            variables.add("X1")
        if "Z" in variables:
            variables.add("Z1")

        max_z = 0
        for variable in variables:
            if variable.startswith("Z") and variable[1:].isdigit():
                max_z = max(max_z, int(variable[1:]))

        return cls(
            used_variables=variables,
            used_labels=labels,
            next_variable_index=max_z + 1,
        )

    def new_variable(self) -> str:
        """Return a fresh Z variable that does not occur in the source."""
        while True:
            name = f"Z{self.next_variable_index}"
            self.next_variable_index += 1
            if name not in self.used_variables:
                self.used_variables.add(name)
                return name

    def new_label(self, stem: str = "STEP") -> str:
        """Return a fresh label that does not occur in the source."""
        safe_stem = re.sub(r"[^A-Za-z0-9_]", "_", stem.upper()) or "STEP"
        if not safe_stem[0].isalpha():
            safe_stem = f"L_{safe_stem}"

        while True:
            name = f"MACRO_{self.next_label_index}_{safe_stem}"
            self.next_label_index += 1
            if name not in self.used_labels:
                self.used_labels.add(name)
                return name


MacroExpander = Callable[[Match[str], MacroExpansionContext], Sequence[str]]


@dataclass(frozen=True)
class MacroDefinition:
    name: str
    pattern: Pattern[str]
    syntax: str
    expander: MacroExpander


class MacroRegistry:
    """Ordered registry of source-level macros."""

    def __init__(self) -> None:
        self._definitions: list[MacroDefinition] = []

    def register(
        self,
        name: str,
        pattern: str,
        syntax: str,
    ) -> Callable[[MacroExpander], MacroExpander]:
        """Register a macro expander using a full-line regular expression."""
        compiled = re.compile(pattern, re.IGNORECASE)
        normalized_name = name.upper()

        def decorator(expander: MacroExpander) -> MacroExpander:
            if any(definition.name.upper() == normalized_name for definition in self._definitions):
                raise MacroExpansionError(f"Macro {name} is already registered.")
            self._definitions.append(
                MacroDefinition(
                    name=name,
                    pattern=compiled,
                    syntax=syntax,
                    expander=expander,
                )
            )
            return expander

        return decorator

    def expand(
        self,
        instruction: str,
        context: MacroExpansionContext,
    ) -> Optional[list[str]]:
        """Expand one macro instruction, or return None when none matches."""
        for definition in self._definitions:
            match = definition.pattern.fullmatch(instruction.strip())
            if match is None:
                continue

            expanded = list(definition.expander(match, context))
            if not expanded:
                raise MacroExpansionError(
                    f"Macro {definition.name} expanded to no instructions."
                )
            if any(not line.strip() for line in expanded):
                raise MacroExpansionError(
                    f"Macro {definition.name} produced an empty instruction."
                )
            return expanded

        return None

    @property
    def syntaxes(self) -> tuple[str, ...]:
        return tuple(definition.syntax for definition in self._definitions)


MACROS = MacroRegistry()


def macro(
    name: str,
    pattern: str,
    syntax: str,
) -> Callable[[MacroExpander], MacroExpander]:
    """Register a macro in the shared registry."""
    return MACROS.register(name, pattern, syntax)
