"""Unconditional GOTO macro."""

from __future__ import annotations

from typing import Match, Sequence

from .registry import IDENTIFIER_PATTERN, MacroExpansionContext, macro


@macro(
    name="GOTO",
    pattern=rf"\s*GOTO\s+(?P<label>{IDENTIFIER_PATTERN})\s*",
    syntax="GOTO L",
)
def expand_goto(match: Match[str], context: MacroExpansionContext) -> Sequence[str]:
    target = match.group("label")
    guard = context.new_variable()
    return (
        f"{guard}++",
        f"IF {guard} != 0 GOTO {target}",
    )
