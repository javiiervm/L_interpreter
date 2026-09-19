#!/usr/bin/env python3
"""
Interpreter for the simple computability language L used in the supplied notes.

Core L instructions:
    V++
    V--
    V==
    IF V != 0 GOTO L

Supported practical macro notation used in the notes:
    GOTO L
    V <- W
    V ← W

Variables:
    X1, X2, ...   input variables
    Z1, Z2, ...   local variables
    Y             output variable

For convenience, X means X1 and Z means Z1, matching examples in the notes.

This tool parses/checks a program and executes it. It is an interpreter rather
than a native-code compiler, although the --check mode can be used as a
"compile/syntax-check" step before running a program.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


# ----------------------------- Errors --------------------------------- #

class LError(Exception):
    """Base class for L-language errors."""


class LSyntaxError(LError):
    """Raised when an L source line has invalid syntax."""


class LRuntimeError(LError):
    """Raised when execution cannot continue normally."""


# ----------------------------- Model ---------------------------------- #

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
    # A label may legally appear more than once. The semantics in the notes
    # jump to the first instruction carrying that label.
    labels: Dict[str, int]
    duplicate_labels: Dict[str, List[int]]
    referenced_labels: List[str]
    variables: List[str]


# ----------------------------- Syntax --------------------------------- #

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

_GOTO_RE = re.compile(
    r"^\s*GOTO\s+([A-Za-z][A-Za-z0-9_]*)\s*$",
    re.IGNORECASE,
)

_ASSIGN_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*(?:<-|←)\s*"
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
    # X with no digits and Z with no digits were handled above.
    return name


def normalize_label(name: str) -> str:
    name = name.upper()
    if not _LABEL_RE.fullmatch(name):
        raise LSyntaxError(f"'{name}' is not a valid label.")
    return name


def strip_comment(line: str) -> str:
    # Comments are an interpreter convenience, not part of the formal language.
    # We support '#' and '//' comments.
    hash_pos = line.find("#")
    slash_pos = line.find("//")

    positions = [p for p in (hash_pos, slash_pos) if p != -1]
    if positions:
        line = line[:min(positions)]
    return line.rstrip()


def parse_source(text: str) -> Program:
    instructions: List[Instruction] = []
    label_occurrences: Dict[str, List[int]] = {}
    referenced_labels: List[str] = []
    vars_seen = set()

    for line_no, original_line in enumerate(text.splitlines(), start=1):
        source = strip_comment(original_line).strip()

        if not source:
            continue

        label: Optional[str] = None
        m = _LABEL_PREFIX_RE.match(source)
        if m:
            label = normalize_label(m.group(1))
            source = m.group(2).strip()

            if not source:
                raise LSyntaxError(
                    f"Line {line_no}: a label must prefix an instruction; "
                    "a label-only line is not an L instruction."
                )

        op: Optional[str] = None
        args: Tuple[str, ...] = ()

        m = _INC_RE.match(source)
        if m:
            v = normalize_var(m.group(1))
            op, args = "INC", (v,)
            vars_seen.add(v)

        if op is None:
            m = _DEC_RE.match(source)
            if m:
                v = normalize_var(m.group(1))
                op, args = "DEC", (v,)
                vars_seen.add(v)

        if op is None:
            m = _NOP_RE.match(source)
            if m:
                v = normalize_var(m.group(1))
                op, args = "NOP", (v,)
                vars_seen.add(v)

        if op is None:
            m = _IF_RE.match(source)
            if m:
                v = normalize_var(m.group(1))
                target = normalize_label(m.group(2))
                op, args = "IFNZ", (v, target)
                vars_seen.add(v)
                referenced_labels.append(target)

        if op is None:
            m = _GOTO_RE.match(source)
            if m:
                target = normalize_label(m.group(1))
                op, args = "GOTO", (target,)
                referenced_labels.append(target)

        if op is None:
            m = _ASSIGN_RE.match(source)
            if m:
                dst = normalize_var(m.group(1))
                src = normalize_var(m.group(2))
                op, args = "ASSIGN", (dst, src)
                vars_seen.add(dst)
                vars_seen.add(src)

        if op is None:
            raise LSyntaxError(
                f"Line {line_no}: cannot parse instruction:\n"
                f"    {original_line}\n"
                "Expected one of: V++, V--, V==, IF V != 0 GOTO L, "
                "GOTO L, or V <- W."
            )

        index = len(instructions)  # zero-based internal program counter
        inst = Instruction(
            line_no=line_no,
            raw=original_line.strip(),
            label=label,
            op=op,
            args=args,
        )
        instructions.append(inst)

        if label is not None:
            label_occurrences.setdefault(label, []).append(index)

    labels = {
        label: indexes[0]
        for label, indexes in label_occurrences.items()
    }
    duplicates = {
        label: indexes
        for label, indexes in label_occurrences.items()
        if len(indexes) > 1
    }

    # Y always exists semantically, even if not explicitly mentioned.
    vars_seen.add("Y")

    def variable_sort_key(v: str):
        if v == "Y":
            return (2, 0)
        prefix = v[0]
        number = int(v[1:]) if len(v) > 1 else 1
        return (0 if prefix == "X" else 1, number)

    variables = sorted(vars_seen, key=variable_sort_key)

    return Program(
        instructions=instructions,
        labels=labels,
        duplicate_labels=duplicates,
        referenced_labels=referenced_labels,
        variables=variables,
    )


# ----------------------------- Execution ------------------------------ #

@dataclass
class ExecutionResult:
    terminated: bool
    step_limit_reached: bool
    steps: int
    state: Dict[str, int]
    pc: int  # zero-based current pc; len(program) means terminal


def make_initial_state(program: Program, inputs: Sequence[int]) -> Dict[str, int]:
    state: Dict[str, int] = {}

    # Every variable appearing in P starts at 0 except supplied X_i inputs.
    for var in program.variables:
        state[var] = 0

    state["Y"] = 0

    for i, value in enumerate(inputs, start=1):
        if value < 0:
            raise LRuntimeError("L works over natural numbers; inputs must be >= 0.")
        state[f"X{i}"] = value

    return state


def get_value(state: Dict[str, int], var: str) -> int:
    # Variables not explicitly present in the program are still conceptually 0.
    return state.get(var, 0)


def set_value(state: Dict[str, int], var: str, value: int) -> None:
    if value < 0:
        raise LRuntimeError("Internal error: L variables cannot become negative.")
    state[var] = value


def format_state(state: Dict[str, int]) -> str:
    def key(v: str):
        if v == "Y":
            return (2, 0)
        if v.startswith("X") and v[1:].isdigit():
            return (0, int(v[1:]))
        if v.startswith("Z") and v[1:].isdigit():
            return (1, int(v[1:]))
        return (3, v)

    return ", ".join(f"{v}={state[v]}" for v in sorted(state, key=key))


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
    n = len(program.instructions)

    if trace:
        print("Initial snapshot:")
        print(f"  (1, {{{format_state(state)}}})" if n else f"  (1, {{{format_state(state)}}}) [terminal]")
        print()

    while pc < n:
        if steps >= max_steps:
            return ExecutionResult(
                terminated=False,
                step_limit_reached=True,
                steps=steps,
                state=state,
                pc=pc,
            )

        inst = program.instructions[pc]
        old_pc = pc
        action = ""

        if inst.op == "INC":
            (v,) = inst.args
            set_value(state, v, get_value(state, v) + 1)
            pc += 1
            action = f"{v} := {state[v]}"

        elif inst.op == "DEC":
            (v,) = inst.args
            old = get_value(state, v)
            set_value(state, v, max(0, old - 1))
            pc += 1
            action = f"{v} := {state[v]}"

        elif inst.op == "NOP":
            pc += 1
            action = "no change"

        elif inst.op == "IFNZ":
            v, target = inst.args
            if get_value(state, v) != 0:
                if target in program.labels:
                    pc = program.labels[target]
                    action = f"jump -> {target} (instruction {pc + 1})"
                else:
                    # Formal semantics from the notes:
                    # if the target label does not exist, execution becomes terminal.
                    pc = n
                    action = f"jump -> missing label {target}; program terminates"
            else:
                pc += 1
                action = f"{v}=0; no jump"

        elif inst.op == "GOTO":
            (target,) = inst.args
            if target in program.labels:
                pc = program.labels[target]
                action = f"jump -> {target} (instruction {pc + 1})"
            else:
                pc = n
                action = f"jump -> missing label {target}; program terminates"

        elif inst.op == "ASSIGN":
            dst, src = inst.args
            set_value(state, dst, get_value(state, src))
            pc += 1
            action = f"{dst} := {state[dst]}"

        else:
            raise LRuntimeError(f"Unknown internal operation: {inst.op}")

        steps += 1

        if trace:
            label_text = f"({inst.label}) " if inst.label else ""
            print(
                f"Step {steps:>5} | i={old_pc + 1:<4} | "
                f"{label_text}{instruction_to_text(inst):<30} | {action}"
            )
            if pc < n:
                print(f"           next: i={pc + 1} | {{{format_state(state)}}}")
            else:
                print(f"           next: terminal | {{{format_state(state)}}}")

    return ExecutionResult(
        terminated=True,
        step_limit_reached=False,
        steps=steps,
        state=state,
        pc=pc,
    )


# ----------------------------- Diagnostics ---------------------------- #

def instruction_to_text(inst: Instruction) -> str:
    if inst.op == "INC":
        return f"{inst.args[0]}++"
    if inst.op == "DEC":
        return f"{inst.args[0]}--"
    if inst.op == "NOP":
        return f"{inst.args[0]}=="
    if inst.op == "IFNZ":
        return f"IF {inst.args[0]} != 0 GOTO {inst.args[1]}"
    if inst.op == "GOTO":
        return f"GOTO {inst.args[0]}"
    if inst.op == "ASSIGN":
        return f"{inst.args[0]} <- {inst.args[1]}"
    return inst.raw


def print_program(program: Program) -> None:
    if not program.instructions:
        print("(empty program)")
        return

    for i, inst in enumerate(program.instructions, start=1):
        label = f"({inst.label}) " if inst.label else ""
        print(f"{i:>4}: {label}{instruction_to_text(inst)}")


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


# ----------------------------- CLI ------------------------------------ #

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
    parser = argparse.ArgumentParser(
        prog="l_interpreter.py",
        description=(
            "Parse and execute programs in the computability language L "
            "used in the supplied course notes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
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

Practical macros accepted by this interpreter:
  GOTO A
  Y <- X1
  Y ← X1

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
        help="Show the execution step by step.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Parse and validate the program without executing it.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the normalized parsed program before execution.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=100_000,
        help="Stop after this many instructions (default: 100000).",
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
            print("Parsed program:")
            print_program(program)
            print()

        if warnings:
            print("Warnings:", file=sys.stderr)
            for warning in warnings:
                print(f"  - {warning}", file=sys.stderr)
            print(file=sys.stderr)

        if args.check:
            print(
                f"OK: {len(program.instructions)} instruction(s), "
                f"{len(program.labels)} distinct label(s)."
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

        print(f"Program terminated after {result.steps} step(s).")
        print(f"Y = {get_value(result.state, 'Y')}")
        return 0

    except LError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
