#!/usr/bin/env python3
"""Interpreter for the simple computability language L used in the course notes.

Core L instructions:
    V++
    V--
    V==
    IF V != 0 GOTO L

Source-level macro notation is provided by the separate ``macros`` module and
expanded to primitive L instructions before parsing and execution.

Variables:
    X1, X2, ...   input variables
    Z1, Z2, ...   local variables
    Y             output variable

For convenience, X means X1 and Z means Z1, matching examples in the notes.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from macros import MACROS, MacroExpansionContext, MacroExpansionError


class LError(Exception):
    """Base class for L-language errors."""


class LSyntaxError(LError):
    """Raised when an L source line has invalid syntax."""


class LRuntimeError(LError):
    """Raised when execution cannot continue normally."""


@dataclass(frozen=True)
class Instruction:
    line_no: int
    raw: str
    label: Optional[str]
    op: str
    args: Tuple[str, ...]


@dataclass
class Program:
    instructions: List[Instruction]
    labels: Dict[str, int]
    duplicate_labels: Dict[str, List[int]]
    referenced_labels: List[str]
    variables: List[str]
    macro_expansions: int


_VAR_RE = re.compile(r"^(?:Y|X\d*|Z\d*)$", re.IGNORECASE)
_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_LABEL_PREFIX_RE = re.compile(
    r"^\s*\(\s*([A-Za-z][A-Za-z0-9_]*)\s*\)\s*(.*?)\s*$"
)
_INC_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*\+\+\s*$", re.IGNORECASE)
_DEC_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*--\s*$", re.IGNORECASE)
_NOP_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*==\s*$", re.IGNORECASE)
_IF_RE = re.compile(
    r"^\s*IF\s+([A-Za-z][A-Za-z0-9_]*)\s*(?:!=|≠)\s*0\s+GOTO\s+"
    r"([A-Za-z][A-Za-z0-9_]*)\s*$",
    re.IGNORECASE,
)


def normalize_var(name: str) -> str:
    name = name.upper()
    if name == "X":
        return "X1"
    if name == "Z":
        return "Z1"
    if not _VAR_RE.fullmatch(name):
        raise LSyntaxError(
            f"'{name}' is not a valid L variable. "
            "Use Y, X/X1/X2/... or Z/Z1/Z2/..."
        )
    return name


def normalize_label(name: str) -> str:
    name = name.upper()
    if not _LABEL_RE.fullmatch(name):
        raise LSyntaxError(f"'{name}' is not a valid label.")
    return name


def strip_comment(line: str) -> str:
    hash_pos = line.find("#")
    slash_pos = line.find("//")
    positions = [p for p in (hash_pos, slash_pos) if p != -1]
    if positions:
        line = line[:min(positions)]
    return line.rstrip()


def _split_label(source: str, line_no: int) -> tuple[Optional[str], str]:
    label: Optional[str] = None
    match = _LABEL_PREFIX_RE.match(source)
    if match:
        label = normalize_label(match.group(1))
        source = match.group(2).strip()
        if not source:
            raise LSyntaxError(
                f"Line {line_no}: a label must prefix an instruction; "
                "a label-only line is not an L instruction."
            )
    return label, source


def _parse_primitive(
    source: str,
    *,
    line_no: int,
    raw: str,
    label: Optional[str],
) -> Instruction:
    op: Optional[str] = None
    args: Tuple[str, ...] = ()

    match = _INC_RE.match(source)
    if match:
        variable = normalize_var(match.group(1))
        op, args = "INC", (variable,)

    if op is None:
        match = _DEC_RE.match(source)
        if match:
            variable = normalize_var(match.group(1))
            op, args = "DEC", (variable,)

    if op is None:
        match = _NOP_RE.match(source)
        if match:
            variable = normalize_var(match.group(1))
            op, args = "NOP", (variable,)

    if op is None:
        match = _IF_RE.match(source)
        if match:
            variable = normalize_var(match.group(1))
            target = normalize_label(match.group(2))
            op, args = "IFNZ", (variable, target)

    if op is None:
        macro_syntax = ", ".join(MACROS.syntaxes)
        raise LSyntaxError(
            f"Line {line_no}: cannot parse instruction:\n"
            f"    {raw}\n"
            "Expected one of the primitive forms V++, V--, V==, "
            f"IF V != 0 GOTO L, or a registered macro ({macro_syntax})."
        )

    return Instruction(line_no, raw.strip(), label, op, args)


def parse_source(text: str) -> Program:
    instructions: List[Instruction] = []
    label_occurrences: Dict[str, List[int]] = {}
    referenced_labels: List[str] = []
    vars_seen = set()
    macro_expansions = 0
    macro_context = MacroExpansionContext.from_source(text)

    for line_no, original_line in enumerate(text.splitlines(), start=1):
        source = strip_comment(original_line).strip()
        if not source:
            continue

        source_label, source = _split_label(source, line_no)

        try:
            expansion = MACROS.expand(source, macro_context)
        except MacroExpansionError as exc:
            raise LSyntaxError(f"Line {line_no}: {exc}") from exc

        if expansion is None:
            expanded_lines = [source]
        else:
            macro_expansions += 1
            expanded_lines = expansion

        for expansion_index, expanded_line in enumerate(expanded_lines):
            expanded_source = expanded_line.strip()
            generated_label, expanded_source = _split_label(expanded_source, line_no)

            label = generated_label
            if expansion_index == 0 and source_label is not None:
                if generated_label is not None:
                    raise LSyntaxError(
                        f"Line {line_no}: macro expansion cannot place an internal label "
                        "on its first instruction when the source instruction is labeled."
                    )
                label = source_label

            instruction = _parse_primitive(
                expanded_source,
                line_no=line_no,
                raw=original_line,
                label=label,
            )
            index = len(instructions)
            instructions.append(instruction)

            if instruction.label is not None:
                label_occurrences.setdefault(instruction.label, []).append(index)

            if instruction.op == "IFNZ":
                variable, target = instruction.args
                vars_seen.add(variable)
                referenced_labels.append(target)
            else:
                vars_seen.add(instruction.args[0])

    labels = {label: indexes[0] for label, indexes in label_occurrences.items()}
    duplicates = {
        label: indexes
        for label, indexes in label_occurrences.items()
        if len(indexes) > 1
    }

    vars_seen.add("Y")

    def variable_sort_key(variable: str):
        if variable == "Y":
            return (2, 0)
        prefix = variable[0]
        number = int(variable[1:]) if len(variable) > 1 else 1
        return (0 if prefix == "X" else 1, number)

    return Program(
        instructions=instructions,
        labels=labels,
        duplicate_labels=duplicates,
        referenced_labels=referenced_labels,
        variables=sorted(vars_seen, key=variable_sort_key),
        macro_expansions=macro_expansions,
    )


@dataclass
class ExecutionResult:
    terminated: bool
    step_limit_reached: bool
    steps: int
    state: Dict[str, int]
    pc: int


def make_initial_state(program: Program, inputs: Sequence[int]) -> Dict[str, int]:
    state = {variable: 0 for variable in program.variables}
    state["Y"] = 0
    for i, value in enumerate(inputs, start=1):
        if value < 0:
            raise LRuntimeError("L works over natural numbers; inputs must be >= 0.")
        state[f"X{i}"] = value
    return state


def get_value(state: Dict[str, int], variable: str) -> int:
    return state.get(variable, 0)


def set_value(state: Dict[str, int], variable: str, value: int) -> None:
    if value < 0:
        raise LRuntimeError("Internal error: L variables cannot become negative.")
    state[variable] = value


def format_state(state: Dict[str, int]) -> str:
    def key(variable: str):
        if variable == "Y":
            return (2, 0)
        if variable.startswith("X") and variable[1:].isdigit():
            return (0, int(variable[1:]))
        if variable.startswith("Z") and variable[1:].isdigit():
            return (1, int(variable[1:]))
        return (3, variable)

    return ", ".join(
        f"{variable}={state[variable]}" for variable in sorted(state, key=key)
    )


def execute(
    program: Program,
    inputs: Sequence[int],
    *,
    max_steps: int = 100_000,
    trace: bool = False,
) -> ExecutionResult:
    if max_steps <= 0:
        raise LRuntimeError("--max-steps must be greater than 0.")

    state = make_initial_state(program, inputs)
    pc = 0
    steps = 0
    instruction_count = len(program.instructions)

    if trace:
        print("Initial snapshot:")
        terminal = " [terminal]" if instruction_count == 0 else ""
        print(f"  (1, {{{format_state(state)}}}){terminal}")
        print()

    while pc < instruction_count:
        if steps >= max_steps:
            return ExecutionResult(False, True, steps, state, pc)

        instruction = program.instructions[pc]
        old_pc = pc
        action = ""

        if instruction.op == "INC":
            (variable,) = instruction.args
            set_value(state, variable, get_value(state, variable) + 1)
            pc += 1
            action = f"{variable} := {state[variable]}"
        elif instruction.op == "DEC":
            (variable,) = instruction.args
            old = get_value(state, variable)
            set_value(state, variable, max(0, old - 1))
            pc += 1
            action = f"{variable} := {state[variable]}"
        elif instruction.op == "NOP":
            pc += 1
            action = "no change"
        elif instruction.op == "IFNZ":
            variable, target = instruction.args
            if get_value(state, variable) != 0:
                if target in program.labels:
                    pc = program.labels[target]
                    action = f"jump -> {target} (instruction {pc + 1})"
                else:
                    pc = instruction_count
                    action = f"jump -> missing label {target}; program terminates"
            else:
                pc += 1
                action = f"{variable}=0; no jump"
        else:
            raise LRuntimeError(f"Unknown internal operation: {instruction.op}")

        steps += 1

        if trace:
            label_text = f"({instruction.label}) " if instruction.label else ""
            print(
                f"Step {steps:>5} | i={old_pc + 1:<4} | "
                f"{label_text}{instruction_to_text(instruction):<30} | {action}"
            )
            if pc < instruction_count:
                print(f"           next: i={pc + 1} | {{{format_state(state)}}}")
            else:
                print(f"           next: terminal | {{{format_state(state)}}}")

    return ExecutionResult(True, False, steps, state, pc)


def instruction_to_text(instruction: Instruction) -> str:
    if instruction.op == "INC":
        return f"{instruction.args[0]}++"
    if instruction.op == "DEC":
        return f"{instruction.args[0]}--"
    if instruction.op == "NOP":
        return f"{instruction.args[0]}=="
    if instruction.op == "IFNZ":
        return f"IF {instruction.args[0]} != 0 GOTO {instruction.args[1]}"
    return instruction.raw


def print_program(program: Program) -> None:
    if not program.instructions:
        print("(empty program)")
        return
    for i, instruction in enumerate(program.instructions, start=1):
        label = f"({instruction.label}) " if instruction.label else ""
        print(f"{i:>4}: {label}{instruction_to_text(instruction)}")


def diagnostics(program: Program) -> List[str]:
    warnings: List[str] = []
    for label, indexes in sorted(program.duplicate_labels.items()):
        display = ", ".join(str(i + 1) for i in indexes)
        warnings.append(
            f"Label {label} appears more than once (instructions {display}). "
            "A jump to it goes to the first occurrence."
        )

    missing = sorted(set(program.referenced_labels) - set(program.labels))
    for label in missing:
        warnings.append(
            f"Label {label} is referenced but not defined. "
            "This is legal under the notes' semantics: taking that jump terminates the program."
        )
    return warnings


def parse_natural(text: str) -> int:
    try:
        value = int(text, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"'{text}' is not an integer.") from exc
    if value < 0:
        raise argparse.ArgumentTypeError(
            f"'{text}' is negative. L inputs must be natural numbers."
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    macro_help = "\n".join(f"  {syntax}" for syntax in MACROS.syntaxes)
    parser = argparse.ArgumentParser(
        prog="l_interpreter.py",
        description=(
            "Parse and execute programs in the computability language L "
            "used in the supplied course notes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python l_interpreter.py identity.l 5
  python l_interpreter.py sum.l 4 7
  python l_interpreter.py identity.l 5 --trace
  python l_interpreter.py program.l --check
  python l_interpreter.py program.l --list

Input values are assigned in order:
  first number  -> X1
  second number -> X2
  third number  -> X3
  ...

Core syntax:
  X1++
  Z1--
  Y==
  IF X1 != 0 GOTO A
  (A) Y++

Registered macros (expanded before execution):
{macro_help}

Conveniences:
  X means X1
  Z means Z1
  # comment
  // comment
""",
    )
    parser.add_argument("program", type=Path, help="Path to the .l source file.")
    parser.add_argument(
        "inputs",
        nargs="*",
        type=parse_natural,
        help="Natural-number inputs assigned to X1, X2, ...",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Show primitive execution step by step after macro expansion.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Expand macros, parse, and validate without executing.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the expanded primitive program before execution.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=100_000,
        help="Stop after this many primitive instructions (default: 100000).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        try:
            text = args.program.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise LRuntimeError(f"Program file not found: {args.program}")
        except OSError as exc:
            raise LRuntimeError(f"Could not read {args.program}: {exc}") from exc

        program = parse_source(text)
        warnings = diagnostics(program)

        if args.list:
            print("Expanded primitive program:")
            print_program(program)
            print()

        if warnings:
            print("Warnings:", file=sys.stderr)
            for warning in warnings:
                print(f"  - {warning}", file=sys.stderr)
            print(file=sys.stderr)

        if args.check:
            print(
                f"OK: {len(program.instructions)} primitive instruction(s), "
                f"{len(program.labels)} distinct label(s), "
                f"{program.macro_expansions} macro expansion(s)."
            )
            return 0

        result = execute(
            program,
            args.inputs,
            max_steps=args.max_steps,
            trace=args.trace,
        )

        if result.step_limit_reached:
            print(
                f"\nStopped after {result.steps} steps: execution did not terminate "
                f"within the configured limit ({args.max_steps}).",
                file=sys.stderr,
            )
            print(
                "This may be an infinite computation (an undefined value), "
                "or simply a program that needs a larger --max-steps limit.",
                file=sys.stderr,
            )
            print(f"Current state: {format_state(result.state)}", file=sys.stderr)
            return 2

        print(f"Program terminated after {result.steps} primitive step(s).")
        print(f"Y = {get_value(result.state, 'Y')}")
        return 0

    except LError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
