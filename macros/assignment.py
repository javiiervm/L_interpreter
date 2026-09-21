"""Variable assignment macro."""

from __future__ import annotations

from typing import Match, Sequence

from .registry import IDENTIFIER_PATTERN, MacroExpansionContext, macro


def _canonical_variable(name: str) -> str:
    name = name.upper()
    if name == "X":
        return "X1"
    if name == "Z":
        return "Z1"
    return name


@macro(
    name="ASSIGN",
    pattern=(
        rf"\s*(?P<dst>{IDENTIFIER_PATTERN})\s*(?:<-|←)\s*"
        rf"(?P<src>{IDENTIFIER_PATTERN})\s*"
    ),
    syntax="V <- W (or V ← W)",
)
def expand_assignment(
    match: Match[str],
    context: MacroExpansionContext,
) -> Sequence[str]:
    dst = match.group("dst")
    src = match.group("src")

    if _canonical_variable(dst) == _canonical_variable(src):
        return (f"{dst}==",)

    temporary = context.new_variable()
    guard = context.new_variable()

    clear_test = context.new_label("ASSIGN_CLEAR_TEST")
    clear_step = context.new_label("ASSIGN_CLEAR_STEP")
    copy_test = context.new_label("ASSIGN_COPY_TEST")
    copy_step = context.new_label("ASSIGN_COPY_STEP")
    restore_test = context.new_label("ASSIGN_RESTORE_TEST")
    restore_step = context.new_label("ASSIGN_RESTORE_STEP")
    done = context.new_label("ASSIGN_DONE")

    return (
        f"{guard}++",
        f"({clear_test}) IF {dst} != 0 GOTO {clear_step}",
        f"IF {guard} != 0 GOTO {copy_test}",
        f"({clear_step}) {dst}--",
        f"IF {guard} != 0 GOTO {clear_test}",
        f"({copy_test}) IF {src} != 0 GOTO {copy_step}",
        f"IF {guard} != 0 GOTO {restore_test}",
        f"({copy_step}) {src}--",
        f"{dst}++",
        f"{temporary}++",
        f"IF {guard} != 0 GOTO {copy_test}",
        f"({restore_test}) IF {temporary} != 0 GOTO {restore_step}",
        f"IF {guard} != 0 GOTO {done}",
        f"({restore_step}) {temporary}--",
        f"{src}++",
        f"IF {guard} != 0 GOTO {restore_test}",
        f"({done}) {dst}==",
    )
