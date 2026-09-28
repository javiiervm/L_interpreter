"""Truncated subtraction macro: V <- W - U."""
from __future__ import annotations
from typing import Match, Sequence
from .registry import IDENTIFIER_PATTERN, MacroExpansionContext, macro

@macro(
    name="SUBTRACT",
    pattern=(rf"\s*(?P<dst>{IDENTIFIER_PATTERN})\s*(?:<-|←)\s*"
             rf"(?P<left>{IDENTIFIER_PATTERN})\s*-\s*(?P<right>{IDENTIFIER_PATTERN})\s*"),
    syntax="V <- W - U (or V ← W - U)",
)
def expand_subtraction(match: Match[str], context: MacroExpansionContext) -> Sequence[str]:
    dst, left, right = match.group("dst"), match.group("left"), match.group("right")
    left_copy=context.new_variable(); right_copy=context.new_variable(); scratch=context.new_variable(); guard=context.new_variable()
    out: list[str] = [f"{guard}++"]

    def copy_preserving(source: str, destination: str, prefix: str) -> None:
        test=context.new_label(f"{prefix}_COPY_TEST"); step=context.new_label(f"{prefix}_COPY_STEP")
        restore_test=context.new_label(f"{prefix}_RESTORE_TEST"); restore_step=context.new_label(f"{prefix}_RESTORE_STEP"); done=context.new_label(f"{prefix}_DONE")
        out.extend((
            f"({test}) IF {source} != 0 GOTO {step}", f"IF {guard} != 0 GOTO {restore_test}",
            f"({step}) {source}--", f"{destination}++", f"{scratch}++", f"IF {guard} != 0 GOTO {test}",
            f"({restore_test}) IF {scratch} != 0 GOTO {restore_step}", f"IF {guard} != 0 GOTO {done}",
            f"({restore_step}) {scratch}--", f"{source}++", f"IF {guard} != 0 GOTO {restore_test}", f"({done}) {destination}==",
        ))

    copy_preserving(left, left_copy, "SUB_LEFT")
    copy_preserving(right, right_copy, "SUB_RIGHT")

    clear_test=context.new_label("SUB_CLEAR_TEST"); clear_step=context.new_label("SUB_CLEAR_STEP")
    sub_test=context.new_label("SUB_TEST"); sub_step=context.new_label("SUB_STEP")
    move_test=context.new_label("SUB_MOVE_TEST"); move_step=context.new_label("SUB_MOVE_STEP"); done=context.new_label("SUB_DONE")
    out.extend((
        f"({clear_test}) IF {dst} != 0 GOTO {clear_step}", f"IF {guard} != 0 GOTO {sub_test}",
        f"({clear_step}) {dst}--", f"IF {guard} != 0 GOTO {clear_test}",
        f"({sub_test}) IF {right_copy} != 0 GOTO {sub_step}", f"IF {guard} != 0 GOTO {move_test}",
        f"({sub_step}) {right_copy}--", f"{left_copy}--", f"IF {guard} != 0 GOTO {sub_test}",
        f"({move_test}) IF {left_copy} != 0 GOTO {move_step}", f"IF {guard} != 0 GOTO {done}",
        f"({move_step}) {left_copy}--", f"{dst}++", f"IF {guard} != 0 GOTO {move_test}", f"({done}) {dst}==",
    ))
    return tuple(out)
