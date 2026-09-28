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
        # Used to implement unconditional jumps.
        #
        # It does not matter if this macro is executed more than once:
        # guard only needs to remain non-zero.
        f"{guard}++",
    ]

    def clear_variable(
        variable: str,
        prefix: str,
    ) -> None:
        """Set an auxiliary variable to zero."""

        clear_test = context.new_label(f"{prefix}_CLEAR_TEST")
        clear_step = context.new_label(f"{prefix}_CLEAR_STEP")
        clear_done = context.new_label(f"{prefix}_CLEAR_DONE")

        instructions.extend(
            (
                f"({clear_test}) IF {variable} != 0 GOTO {clear_step}",
                f"IF {guard} != 0 GOTO {clear_done}",

                f"({clear_step}) {variable}--",
                f"IF {guard} != 0 GOTO {clear_test}",

                f"({clear_done}) {variable}==",
            )
        )

    def copy_preserving(
        source: str,
        destination: str,
        prefix: str,
    ) -> None:
        """Copy source into destination without changing source.

        destination must initially be zero.
        scratch must initially be zero.
        """

        copy_test = context.new_label(f"{prefix}_COPY_TEST")
        copy_step = context.new_label(f"{prefix}_COPY_STEP")
        restore_test = context.new_label(f"{prefix}_RESTORE_TEST")
        restore_step = context.new_label(f"{prefix}_RESTORE_STEP")
        done = context.new_label(f"{prefix}_DONE")

        instructions.extend(
            (
                # Copy source -> destination and scratch.
                f"({copy_test}) IF {source} != 0 GOTO {copy_step}",
                f"IF {guard} != 0 GOTO {restore_test}",

                f"({copy_step}) {source}--",
                f"{destination}++",
                f"{scratch}++",
                f"IF {guard} != 0 GOTO {copy_test}",

                # Restore source from scratch.
                f"({restore_test}) IF {scratch} != 0 GOTO {restore_step}",
                f"IF {guard} != 0 GOTO {done}",

                f"({restore_step}) {scratch}--",
                f"{source}++",
                f"IF {guard} != 0 GOTO {restore_test}",

                f"({done}) {destination}==",
            )
        )

    # IMPORTANT:
    #
    # A macro instruction may be executed repeatedly if it is inside a loop.
    # Therefore, auxiliary variables cannot be assumed to still contain zero
    # just because every Z variable starts at zero when the program begins.
    #
    # In the previous implementation, left_copy retained its value from the
    # previous execution. For example:
    #
    #     X3 <- Y * Y
    #
    # executed first with Y=1 left left_copy=1. When it was executed again
    # with Y=2, another 2 was copied into left_copy, producing 3 instead of 2.
    #
    # Reset all reusable temporaries before starting a new multiplication.
    clear_variable(left_copy, "MULT_LEFT_COPY")
    clear_variable(right_copy, "MULT_RIGHT_COPY")
    clear_variable(add_copy, "MULT_ADD_COPY")
    clear_variable(scratch, "MULT_SCRATCH")

    # Preserve both original operands before modifying dst.
    #
    # This also allows cases such as:
    #
    #     X1 <- X1 * X2
    #
    # because X1 is copied before the destination is cleared.
    copy_preserving(left, left_copy, "MULT_LEFT")
    copy_preserving(right, right_copy, "MULT_RIGHT")

    # Clear destination.
    clear_test = context.new_label("MULT_CLEAR_TEST")
    clear_step = context.new_label("MULT_CLEAR_STEP")
    outer_test = context.new_label("MULT_OUTER_TEST")

    instructions.extend(
        (
            f"({clear_test}) IF {dst} != 0 GOTO {clear_step}",
            f"IF {guard} != 0 GOTO {outer_test}",

            f"({clear_step}) {dst}--",
            f"IF {guard} != 0 GOTO {clear_test}",
        )
    )

    # Multiplication by repeated addition:
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
