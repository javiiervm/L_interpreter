"""Formal numeric encoding for expanded L programs.

The primitive coding matches the scheme used by the UA reference platform:
Y=0, X_i=2i-1, Z_i=2i; NOP/INC/DEC are 0/1/2 and a conditional is
2 + code(target-label). Instruction triples are paired with
2^a(2b+1)-1, and a program is encoded by prime powers minus one.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import re
from typing import Dict, List

from l_interpreter import Program, instruction_to_text

_CANONICAL_LABEL_RE = re.compile(r"^(A|B|C|D|S)([1-9]\d*)$", re.IGNORECASE)
_PREFIXES = ("A", "B", "C", "D", "S")

@dataclass(frozen=True)
class EncodedInstruction:
    index: int
    text: str
    label: str | None
    code: int

@dataclass(frozen=True)
class ProgramEncoding:
    instructions: List[EncodedInstruction]
    program_code: int | None
    estimated_program_bits: int
    label_mapping: Dict[str, str]

def label_code(label: str) -> int:
    match = _CANONICAL_LABEL_RE.fullmatch(label.upper())
    if not match:
        raise ValueError(f"Label {label!r} is not in canonical A/B/C/D/S + index form.")
    prefix, index_text = match.groups(); index = int(index_text)
    return _PREFIXES.index(prefix.upper()) + 1 + 5 * (index - 1)

def variable_code(variable: str) -> int:
    variable = variable.upper()
    if variable == "Y": return 0
    if variable.startswith("X") and variable[1:].isdigit() and int(variable[1:]) >= 1:
        return 1 + 2 * (int(variable[1:]) - 1)
    if variable.startswith("Z") and variable[1:].isdigit() and int(variable[1:]) >= 1:
        return 2 + 2 * (int(variable[1:]) - 1)
    raise ValueError(f"Cannot encode variable {variable!r}.")

def num_pair(a: int, b: int) -> int:
    return (2 ** a) * (2 * b + 1) - 1

def instruction_code(label: int, operation: int, variable: int) -> int:
    return num_pair(label, num_pair(operation, variable))

def is_prime(n: int) -> bool:
    if n < 2: return False
    for i in range(2, math.isqrt(n) + 1):
        if n % i == 0: return False
    return True

def nth_prime(n: int) -> int:
    if n < 1: raise ValueError("n must be >= 1")
    count=0; candidate=1
    while count < n:
        candidate += 1
        if is_prime(candidate): count += 1
    return candidate

def estimate_program_bits(codes: List[int]) -> int:
    if not codes:
        return 1
    return int(sum(code * math.log2(nth_prime(i)) for i, code in enumerate(codes, start=1))) + 1

def encode_program_number(codes: List[int]) -> int:
    """Return the exact prime-power program code.

    This can be astronomically large for expanded macro programs; callers
    should inspect ``estimate_program_bits`` before requesting it blindly.
    """
    value = 1
    for i, code in enumerate(codes, start=1):
        value *= nth_prime(i) ** code
    return value - 1

def _canonical_name(sequence_index: int) -> str:
    q, r = divmod(sequence_index, len(_PREFIXES))
    return f"{_PREFIXES[r]}{q + 1}"

def _build_label_mapping(program: Program) -> tuple[dict[str, str], dict[int, str]]:
    by_target: dict[int, list[str]] = {}
    for label, target in program.labels.items():
        by_target.setdefault(target, []).append(label)

    # Reserve canonical names already written by the user before assigning names
    # to descriptive/generated labels. This keeps A1/B1/... stable even when a
    # descriptive label appears earlier in the program.
    reserved = {
        label.upper()
        for label in list(program.labels) + list(program.referenced_labels)
        if _CANONICAL_LABEL_RE.fullmatch(label)
    }
    used: set[str] = set()
    mapping: dict[str, str] = {}
    target_name: dict[int, str] = {}

    def fresh_canonical() -> str:
        i = 0
        while _canonical_name(i) in used or _canonical_name(i) in reserved:
            i += 1
        return _canonical_name(i)

    for target in sorted(by_target):
        labels = by_target[target]
        preferred = next((x.upper() for x in labels if _CANONICAL_LABEL_RE.fullmatch(x)), None)
        canonical = preferred if preferred is not None else fresh_canonical()
        used.add(canonical); target_name[target] = canonical
        for label in labels: mapping[label] = canonical

    # Referenced-but-undefined labels must stay absent from instruction labels;
    # giving each one an unused canonical name preserves terminating jumps.
    for label in program.referenced_labels:
        if label in mapping: continue
        if _CANONICAL_LABEL_RE.fullmatch(label):
            canonical = label.upper()
        else:
            canonical = fresh_canonical()
        used.add(canonical); mapping[label] = canonical

    return mapping, target_name

def encode_program(program: Program) -> ProgramEncoding:
    mapping, target_names = _build_label_mapping(program)
    encoded: list[EncodedInstruction] = []
    codes: list[int] = []

    for index, instruction in enumerate(program.instructions):
        canonical_label = target_names.get(index)
        a = label_code(canonical_label) if canonical_label else 0
        if instruction.op == "NOP": operation = 0; variable = instruction.args[0]
        elif instruction.op == "INC": operation = 1; variable = instruction.args[0]
        elif instruction.op == "DEC": operation = 2; variable = instruction.args[0]
        elif instruction.op == "IFNZ":
            variable, target = instruction.args
            operation = 2 + label_code(mapping[target])
        else:
            raise ValueError(f"Unsupported internal operation {instruction.op!r}")
        code = instruction_code(a, operation, variable_code(variable))
        codes.append(code)
        encoded.append(EncodedInstruction(index + 1, instruction_to_text(instruction), canonical_label, code))

    estimated_bits = estimate_program_bits(codes)
    # Keep --encode safe on macro-expanded programs. The exact instruction
    # codes are always returned, while the whole-program integer is materialized
    # only when it is reasonably sized. ``encode_program_number`` remains
    # available for callers that explicitly want the exact huge integer.
    program_code = encode_program_number(codes) if estimated_bits <= 2_000_000 else None
    return ProgramEncoding(encoded, program_code, estimated_bits, mapping)

def format_encoding(encoding: ProgramEncoding) -> str:
    lines = ["Encoding:"]
    if encoding.label_mapping:
        lines.append("  Label mapping: " + ", ".join(f"{k}->{v}" for k, v in sorted(encoding.label_mapping.items())))
    for item in encoding.instructions:
        prefix = f"{item.label}: " if item.label else ""
        lines.append(f"  {item.index}: {prefix}{item.text} => {item.code}")
    if encoding.program_code is None:
        lines.append(
            "  Program code: omitted from display/computation because the exact "
            f"integer is estimated at {encoding.estimated_program_bits:,} bits"
        )
    else:
        lines.append(f"  Program code: {encoding.program_code}")
    return "\n".join(lines)
