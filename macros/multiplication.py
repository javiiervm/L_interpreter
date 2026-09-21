"""Multiplication assignment macro: V <- W * U."""

from __future__ import annotations

from typing import Match, Sequence

from .registry import (
    IDENTIFIER_PATTERN,
    MacroExpansionContext,
    macro,
)


@macro(
    name="MULTIPLY",
    pattern=(
        rf"\s*(?P<dst>{IDENTIFIER_PATTERN})\s*(?:<-|←)\s*"
        rf"(?P<left>{IDENTIFIER_PATTERN})\s*\*\s*"
        rf"(?P<right>{IDENTIFIER_PATTERN})\s*"
    ),
    syntax="V <- W * U (or V ← W * U)",
)
def expand_multiplication(
    match: Match[str],
    context: MacroExpansionContext,
) -> Sequence[str]:
    dst = match.group("dst")
    left = match.group("left")
    right = match.group("right")

    # Copies of the original operands.
    left_copy = context.new_variable()
    right_copy = context.new_variable()

    # Temporary variables used internally.
    add_copy = context.new_variable()
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
        """Copy source into destination without changing source."""

        copy_test = context.new_label(f"{prefix}_COPY_TEST")
        copy_step = context.new_label(f"{prefix}_COPY_STEP")
        restore_test = context.new_label(f"{prefix}_RESTORE_TEST")
        restore_step = context.new_label(f"{prefix}_RESTORE_STEP")
        done = context.new_label(f"{prefix}_DONE")

        instructions.extend(
            (
                f"({copy_test}) IF {source} != 0 GOTO {copy_step}",
                f"IF {guard} != 0 GOTO {restore_test}",

                f"({copy_step}) {source}--",
                f"{destination}++",
                f"{scratch}++",
                f"IF {guard} != 0 GOTO {copy_test}",

                f"({restore_test}) IF {scratch} != 0 GOTO {restore_step}",
                f"IF {guard} != 0 GOTO {done}",

                f"({restore_step}) {scratch}--",
                f"{source}++",
                f"IF {guard} != 0 GOTO {restore_test}",

                f"({done}) {destination}==",
            )
        )

    # Preserve both original operands before modifying dst.
    #
    # This makes cases such as:
    #
    #     X1 <- X1 * X2
    #
    # work correctly.
    copy_preserving(left, left_copy, "MULT_LEFT")
    copy_preserving(right, right_copy, "MULT_RIGHT")

    # Clear destination.
    clear_test = context.new_label("MULT_CLEAR_TEST")
    clear_step = context.new_label("MULT_CLEAR_STEP")

    instructions.extend(
        (
            f"({clear_test}) IF {dst} != 0 GOTO {clear_step}",
        )
    )

    outer_test = context.new_label("MULT_OUTER_TEST")

    instructions.extend(
        (
            f"IF {guard} != 0 GOTO {outer_test}",

            f"({clear_step}) {dst}--",
            f"IF {guard} != 0 GOTO {clear_test}",
        )
    )

    # Multiplication is repeated addition:
    #
    #     dst = 0
    #
    #     while right_copy != 0:
    #         dst += left_copy
    #         right_copy--
    #
    outer_step = context.new_label("MULT_OUTER_STEP")

    copy_test = context.new_label("MULT_ADD_COPY_TEST")
    copy_step = context.new_label("MULT_ADD_COPY_STEP")

    restore_test = context.new_label("MULT_ADD_RESTORE_TEST")
    restore_step = context.new_label("MULT_ADD_RESTORE_STEP")

    add_test = context.new_label("MULT_ADD_TEST")
    add_step = context.new_label("MULT_ADD_STEP")

    done = context.new_label("MULT_DONE")

    instructions.extend(
        (
            # Is another multiplication iteration required?
            f"({outer_test}) IF {right_copy} != 0 GOTO {outer_step}",
            f"IF {guard} != 0 GOTO {done}",

            # Consume one unit of the multiplier.
            f"({outer_step}) {right_copy}--",

            # Copy left_copy into add_copy while preserving left_copy.
            f"({copy_test}) IF {left_copy} != 0 GOTO {copy_step}",
            f"IF {guard} != 0 GOTO {restore_test}",

            f"({copy_step}) {left_copy}--",
            f"{add_copy}++",
            f"{scratch}++",
            f"IF {guard} != 0 GOTO {copy_test}",

            # Restore left_copy.
            f"({restore_test}) IF {scratch} != 0 GOTO {restore_step}",
            f"IF {guard} != 0 GOTO {add_test}",

            f"({restore_step}) {scratch}--",
            f"{left_copy}++",
            f"IF {guard} != 0 GOTO {restore_test}",

            # Add left_copy to dst by consuming add_copy.
            f"({add_test}) IF {add_copy} != 0 GOTO {add_step}",
            f"IF {guard} != 0 GOTO {outer_test}",

            f"({add_step}) {add_copy}--",
            f"{dst}++",
            f"IF {guard} != 0 GOTO {add_test}",

            f"({done}) {dst}==",
        )
    )

    return tuple(instructions)
