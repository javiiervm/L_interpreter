#!/usr/bin/env python3
"""Interpreter for the computability language L used in the course notes.

Primitive L instructions:
    V++
    V--
    V==
    IF V != 0 GOTO L

The interpreter also supports two macro layers:

* Registered Python macros from ``macros/`` (assignment, arithmetic, GOTO, ...).
* Source-defined macros compatible with the UA testing platform::

      MACRO NAME
      ... T1, T2 ... W1, W2 ... G1, G2 ... F ...
      END

      CALL NAME ARG1 ARG2 ...

``Tn`` denotes the nth call argument, ``Wn`` a fresh auxiliary Z variable,
``Gn`` a fresh local label and ``F`` the continuation label immediately after
that macro invocation.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from macros import MACROS, MacroExpansionContext, MacroExpansionError


MAX_EXPANSION_DEPTH = 200


class LError(Exception):
    """Base class for L-language errors."""


class LSyntaxError(LError):
    """Raised when L source has invalid syntax."""


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


@dataclass(frozen=True)
class _SourceLine:
    line_no: int
    text: str
    raw: str


@dataclass(frozen=True)
class _SourceMacro:
    name: str
    body: Tuple[_SourceLine, ...]
    definition_line: int


# X and Z are accepted as aliases for X1 and Z1. X0/Z0 are intentionally
# rejected: the language numbers variables from 1.
_VAR_RE = re.compile(r"^(?:Y|X(?:[1-9]\d*)?|Z(?:[1-9]\d*)?)$", re.IGNORECASE)
_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_PAREN_LABEL_PREFIX_RE = re.compile(
    r"^\s*\(\s*([A-Za-z][A-Za-z0-9_]*)\s*\)\s*(.*?)\s*$"
)
_COLON_LABEL_PREFIX_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$"
)
_INC_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*\+\+\s*$", re.IGNORECASE)
_DEC_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*--\s*$", re.IGNORECASE)
_NOP_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*==\s*$", re.IGNORECASE)
_IF_RE = re.compile(
    r"^\s*IF\s+([A-Za-z][A-Za-z0-9_]*)\s*(?:!=|≠)\s*0\s+GOTO\s+"
    r"([A-Za-z][A-Za-z0-9_]*)\s*$",
    re.IGNORECASE,
)
_MACRO_START_RE = re.compile(
    r"^\s*MACRO\s+([A-Za-z][A-Za-z0-9_]*)\s*$", re.IGNORECASE
)
_CALL_RE = re.compile(
    r"^\s*CALL\s+([A-Za-z][A-Za-z0-9_]*)(?:\s+(.*?))?\s*$", re.IGNORECASE
)
_PLACEHOLDER_RE = re.compile(r"\b(?:T[1-9]\d*|W[1-9]\d*|G[1-9]\d*|F)\b", re.IGNORECASE)


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
    """Remove # or // comments from one source line."""
    hash_pos = line.find("#")
    slash_pos = line.find("//")
    positions = [p for p in (hash_pos, slash_pos) if p != -1]
    if positions:
        line = line[: min(positions)]
    return line.rstrip()


def _split_label(source: str) -> tuple[Optional[str], str]:
    """Split either ``(LABEL) instruction`` or ``LABEL: instruction``."""
    for regex in (_PAREN_LABEL_PREFIX_RE, _COLON_LABEL_PREFIX_RE):
        match = regex.match(source)
        if match:
            return normalize_label(match.group(1)), match.group(2).strip()
    return None, source.strip()


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
        op, args = "INC", (normalize_var(match.group(1)),)

    if op is None:
        match = _DEC_RE.match(source)
        if match:
            op, args = "DEC", (normalize_var(match.group(1)),)

    if op is None:
        match = _NOP_RE.match(source)
        if match:
            op, args = "NOP", (normalize_var(match.group(1)),)

    if op is None:
        match = _IF_RE.match(source)
        if match:
            op, args = (
                "IFNZ",
                (normalize_var(match.group(1)), normalize_label(match.group(2))),
            )

    if op is None:
        macro_syntax = ", ".join(MACROS.syntaxes)
        raise LSyntaxError(
            f"Line {line_no}: cannot parse instruction:\n"
            f"    {raw}\n"
            "Expected V++, V--, V==, IF V != 0 GOTO L, CALL NAME ..., "
            f"or a registered macro ({macro_syntax})."
        )

    return Instruction(line_no, raw.strip(), label, op, args)


def _source_lines(text: str) -> list[_SourceLine]:
    lines: list[_SourceLine] = []
    for line_no, original in enumerate(text.splitlines(), start=1):
        cleaned = strip_comment(original).strip()
        if cleaned:
            lines.append(_SourceLine(line_no, cleaned, original))
    return lines


def _extract_source_macros(
    lines: Sequence[_SourceLine],
) -> tuple[dict[str, _SourceMacro], list[_SourceLine]]:
    macros: dict[str, _SourceMacro] = {}
    main_lines: list[_SourceLine] = []
    current_name: Optional[str] = None
    current_line = 0
    current_body: list[_SourceLine] = []

    for line in lines:
        start = _MACRO_START_RE.fullmatch(line.text)
        if start:
            if current_name is not None:
                raise LSyntaxError(
                    f"Line {line.line_no}: cannot define macro {start.group(1)} "
                    f"inside macro {current_name}."
                )
            name = start.group(1).upper()
            if name in macros:
                raise LSyntaxError(
                    f"Line {line.line_no}: macro {name} is already defined."
                )
            current_name = name
            current_line = line.line_no
            current_body = []
            continue

        if line.text.upper() == "END":
            if current_name is None:
                raise LSyntaxError(
                    f"Line {line.line_no}: END found outside a MACRO definition."
                )
            macros[current_name] = _SourceMacro(
                current_name, tuple(current_body), current_line
            )
            current_name = None
            current_line = 0
            current_body = []
            continue

        if current_name is None:
            main_lines.append(line)
        else:
            current_body.append(line)

    if current_name is not None:
        raise LSyntaxError(
            f"Line {current_line}: macro {current_name} has no matching END."
        )

    return macros, main_lines


def _replace_macro_placeholders(
    text: str,
    *,
    macro: _SourceMacro,
    args: Sequence[str],
    context: MacroExpansionContext,
    local_variables: dict[str, str],
    local_labels: dict[str, str],
    exit_label: str,
    call_line: int,
) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(0).upper()
        kind = token[0]

        if kind == "T":
            index = int(token[1:]) - 1
            if index >= len(args):
                raise LSyntaxError(
                    f"Line {call_line}: CALL {macro.name} is missing argument {token}."
                )
            return args[index]

        if kind == "W":
            if token not in local_variables:
                local_variables[token] = context.new_variable()
            return local_variables[token]

        if kind == "G":
            if token not in local_labels:
                local_labels[token] = context.new_label(f"{macro.name}_{token}")
            return local_labels[token]

        return exit_label  # F

    return _PLACEHOLDER_RE.sub(replace, text)


def _expand_lines(
    lines: Sequence[_SourceLine],
    *,
    source_macros: dict[str, _SourceMacro],
    context: MacroExpansionContext,
    depth: int = 0,
    call_stack: tuple[str, ...] = (),
) -> tuple[list[_SourceLine], int]:
    if depth > MAX_EXPANSION_DEPTH: 
        raise LSyntaxError(
            f"Macro expansion exceeded {MAX_EXPANSION_DEPTH} nested expansions. "
            "Check for recursive registered macros."
        )

    result: list[_SourceLine] = []
    expansion_count = 0

    for line in lines:
        source_label, body = _split_label(line.text)

        # A standalone label is legal and applies to the next primitive
        # instruction (or to the terminal position at end of program).
        if source_label is not None and not body:
            result.append(_SourceLine(line.line_no, f"{source_label}:", line.raw))
            continue

        call = _CALL_RE.fullmatch(body)
        if call:
            macro_name = call.group(1).upper()
            macro = source_macros.get(macro_name)
            if macro is None:
                raise LSyntaxError(
                    f"Line {line.line_no}: macro {macro_name} is not defined."
                )
            if macro_name in call_stack:
                chain = " -> ".join((*call_stack, macro_name))
                raise LSyntaxError(
                    f"Line {line.line_no}: recursive source macro call detected: {chain}."
                )

            arg_text = (call.group(2) or "").strip()
            args = arg_text.split() if arg_text else []
            local_variables: dict[str, str] = {}
            local_labels: dict[str, str] = {}
            exit_label = context.new_label(f"{macro.name}_F")

            instantiated: list[_SourceLine] = []
            for macro_line in macro.body:
                translated = _replace_macro_placeholders(
                    macro_line.text,
                    macro=macro,
                    args=args,
                    context=context,
                    local_variables=local_variables,
                    local_labels=local_labels,
                    exit_label=exit_label,
                    call_line=line.line_no,
                )
                instantiated.append(
                    _SourceLine(
                        macro_line.line_no,
                        translated,
                        f"CALL {macro_name} @ line {line.line_no}: {macro_line.raw}",
                    )
                )

            expanded, nested_count = _expand_lines(
                instantiated,
                source_macros=source_macros,
                context=context,
                depth=depth + 1,
                call_stack=(*call_stack, macro_name),
            )

            if source_label is not None:
                result.append(_SourceLine(line.line_no, f"{source_label}:", line.raw))
            result.extend(expanded)
            result.append(_SourceLine(line.line_no, f"{exit_label}:", line.raw))
            expansion_count += 1 + nested_count
            continue

        try:
            registered = MACROS.expand(body, context)
        except MacroExpansionError as exc:
            raise LSyntaxError(f"Line {line.line_no}: {exc}") from exc

        if registered is not None:
            generated = [
                _SourceLine(line.line_no, generated_line.strip(), line.raw)
                for generated_line in registered
            ]
            expanded, nested_count = _expand_lines(
                generated,
                source_macros=source_macros,
                context=context,
                depth=depth + 1,
                call_stack=call_stack,
            )
            if source_label is not None:
                result.append(_SourceLine(line.line_no, f"{source_label}:", line.raw))
            result.extend(expanded)
            expansion_count += 1 + nested_count
            continue

        if source_label is not None:
            result.append(
                _SourceLine(line.line_no, f"{source_label}: {body}", line.raw)
            )
        else:
            result.append(_SourceLine(line.line_no, body, line.raw))

    return result, expansion_count


def parse_source(text: str) -> Program:
    original_lines = _source_lines(text)
    source_macros, main_lines = _extract_source_macros(original_lines)
    macro_context = MacroExpansionContext.from_source(text)
    expanded_lines, macro_expansions = _expand_lines(
        main_lines,
        source_macros=source_macros,
        context=macro_context,
    )

    instructions: List[Instruction] = []
    label_occurrences: Dict[str, List[int]] = {}
    referenced_labels: List[str] = []
    vars_seen: set[str] = set()
    pending_labels: list[tuple[str, int]] = []

    for line in expanded_lines:
        label, source = _split_label(line.text)
        if label is not None and not source:
            pending_labels.append((label, line.line_no))
            continue

        labels_here = list(pending_labels)
        pending_labels.clear()
        if label is not None:
            labels_here.append((label, line.line_no))

        display_label = labels_here[0][0] if labels_here else None
        instruction = _parse_primitive(
            source,
            line_no=line.line_no,
            raw=line.raw,
            label=display_label,
        )
        index = len(instructions)
        instructions.append(instruction)

        for current_label, _ in labels_here:
            label_occurrences.setdefault(current_label, []).append(index)

        if instruction.op == "IFNZ":
            variable, target = instruction.args
            vars_seen.add(variable)
            referenced_labels.append(target)
        else:
            vars_seen.add(instruction.args[0])

    # Labels at EOF point to the terminal program position. A taken jump to
    # one therefore terminates, just like jumping past the last instruction.
    terminal_index = len(instructions)
    for label, _ in pending_labels:
        label_occurrences.setdefault(label, []).append(terminal_index)

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
        number = int(variable[1:])
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
    max_steps: int = 1_000_000,
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
                    if pc < instruction_count:
                        action = f"jump -> {target} (instruction {pc + 1})"
                    else:
                        action = f"jump -> {target} (terminal)"
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
    labels_by_index: dict[int, list[str]] = {}
    for label, index in program.labels.items():
        labels_by_index.setdefault(index, []).append(label)

    for i, instruction in enumerate(program.instructions):
        labels = labels_by_index.get(i, [])
        label_text = " ".join(f"({label})" for label in labels)
        if label_text:
            label_text += " "
        print(f"{i + 1:<4}: {label_text}{instruction_to_text(instruction)}")

    terminal_labels = labels_by_index.get(len(program.instructions), [])
    for label in terminal_labels:
        print(f"     {label}:  [terminal]")


def diagnostics(program: Program) -> List[str]:
    warnings: List[str] = []
    for label, indexes in sorted(program.duplicate_labels.items()):
        display = ", ".join(
            "terminal" if i == len(program.instructions) else str(i + 1)
            for i in indexes
        )
        warnings.append(
            f"Label {label} appears more than once ({display}). "
            "A jump to it goes to the first occurrence."
        )

    missing = sorted(set(program.referenced_labels) - set(program.labels))
    for label in missing:
        warnings.append(
            f"Label {label} is referenced but not defined. "
            "Taking that jump terminates the program."
        )
    return warnings


def parse_natural(text: str) -> int:
    try:
        value = int(text, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"'{text}' is not an integer.") from exc
    if value < 0:
        raise argparse.ArgumentTypeError(
            f"'{text}' is negative. L"
            "inputs must be natural numbers."
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    macro_help = "\n".join(f"  {syntax}" for syntax in MACROS.syntaxes)
    parser = argparse.ArgumentParser(
        prog="l_interpreter.py",
        description=(
            "Parse, expand and execute programs in the computability language L."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python l_interpreter.py identity.l 5
  python l_interpreter.py sum.l 4 7
  python l_interpreter.py identity.l 5 --trace
  python l_interpreter.py program.l --check --list
  python l_interpreter.py program.l --encode

Core syntax:
  X1++
  Z1--
  Y==
  IF X1 != 0 GOTO A1
  A1: Y++
  (A1) Y++

Source macros:
  MACRO COPY
  ... T1, W1, G1 and F ...
  END
  CALL COPY X1 Y

Registered macros:
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
        help="Expand macros, parse and validate without executing.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the fully expanded primitive program.",
    )
    parser.add_argument(
        "--encode",
        action="store_true",
        help="Print the formal numeric encoding of the expanded primitive program.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=1_000_000,
        help="Stop after this many primitive instructions (default: 1000000).",
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

        if args.encode:
            from encoder import encode_program, format_encoding

            print(format_encoding(encode_program(program)))
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
