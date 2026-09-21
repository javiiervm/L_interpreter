"""Addition assignment macro: V <- W + U."""

from __future__ import annotations

from typing import Match, Sequence

from .registry import (
    IDENTIFIER_PATTERN,
    MacroExpansionContext,
    macro,
)


@macro(
    name="ADD",
    pattern=(
        rf"\s*(?P<dst>{IDENTIFIER_PATTERN})\s*(?:<-|←)\s*"
        rf"(?P<left>{IDENTIFIER_PATTERN})\s*\+\s*"
        rf"(?P<right>{IDENTIFIER_PATTERN})\s*"
    ),
    syntax="V <- W + U (or V ← W + U)",
)
def expand_addition(
    match: Match[str],
    context: MacroExpansionContext,
) -> Sequence[str]:
    dst = match.group("dst")
    left = match.group("left")
    right = match.group("right")

    left_copy = context.new_variable()
    right_copy = context.new_variable()
    scratch = context.new_variable()
    guard = context.new_variable()

    instructions: list[str] = [
        f"{guard}++",
    ]

    def copy_preserving(
        source: str,
        destination: str,
        prefix: str,
    ) -> None:
        test = context.new_label(f"{prefix}_COPY_TEST")
        step = context.new_label(f"{prefix}_COPY_STEP")
        restore_test = context.new_label(f"{prefix}_RESTORE_TEST")
        restore_step = context.new_label(f"{prefix}_RESTORE_STEP")
        done = context.new_label(f"{prefix}_COPY_DONE")

        instructions.extend(
            (
                f"({test}) IF {source} != 0 GOTO {step}",
                f"IF {guard} != 0 GOTO {restore_test}",

                f"({step}) {source}--",
                f"{destination}++",
                f"{scratch}++",
                f"IF {guard} != 0 GOTO {test}",

                f"({restore_test}) IF {scratch} != 0 GOTO {restore_step}",
                f"IF {guard} != 0 GOTO {done}",

                f"({restore_step}) {scratch}--",
                f"{source}++",
                f"IF {guard} != 0 GOTO {restore_test}",

                f"({done}) {destination}==",
            )
        )

    # Save both operands before modifying dst.
    #
    # This is important because the destination may also be one of the
    # operands, for example:
    #
    #     X1 <- X1 + X2
    #
    copy_preserving(left, left_copy, "ADD_LEFT")
    copy_preserving(right, right_copy, "ADD_RIGHT")

    clear_test = context.new_label("ADD_CLEAR_TEST")
    clear_step = context.new_label("ADD_CLEAR_STEP")

    left_test = context.new_label("ADD_LEFT_TEST")
    left_step = context.new_label("ADD_LEFT_STEP")

    right_test = context.new_label("ADD_RIGHT_TEST")
    right_step = context.new_label("ADD_RIGHT_STEP")

    done = context.new_label("ADD_DONE")

    instructions.extend(
        (
            # Clear destination.
            f"({clear_test}) IF {dst} != 0 GOTO {clear_step}",
            f"IF {guard} != 0 GOTO {left_test}",

            f"({clear_step}) {dst}--",
            f"IF {guard} != 0 GOTO {clear_test}",

            # Add the saved left operand.
            f"({left_test}) IF {left_copy} != 0 GOTO {left_step}",
            f"IF {guard} != 0 GOTO {right_test}",

            f"({left_step}) {left_copy}--",
            f"{dst}++",
            f"IF {guard} != 0 GOTO {left_test}",

            # Add the saved right operand.
            f"({right_test}) IF {right_copy} != 0 GOTO {right_step}",
            f"IF {guard} != 0 GOTO {done}",

            f"({right_step}) {right_copy}--",
            f"{dst}++",
            f"IF {guard} != 0 GOTO {right_test}",

            f"({done}) {dst}==",
        )
    )

    return tuple(instructions)
