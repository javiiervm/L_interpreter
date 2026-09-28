# L Interpreter

A Python command-line interpreter for **L**, the minimal language used in Teoría de la Computación. It executes the primitive language from the course notes while also supporting the macro notation used by the UA testing platform.

The project keeps the runtime small: every macro is expanded to primitive L before execution. This makes it useful both for checking exercises and for inspecting how higher-level operations reduce to the formal language.

## Features

- Executes all four primitive L instructions: `V++`, `V--`, `V==` and `IF V != 0 GOTO L`.
- Uses natural-number semantics (`V--` leaves zero unchanged).
- Accepts both label styles used across the notes/tools: `(A1) Y++` and `A1: Y++`.
- Accepts standalone labels such as `A1:`; they label the next instruction, or the terminal position at EOF.
- Supports UA-style source macros with `MACRO ... END` and `CALL`.
- Implements source-macro placeholders `T1/T2/...`, local auxiliaries `W1/W2/...`, local labels `G1/G2/...`, and continuation label `F`.
- Supports nested macro calls and detects recursive source-macro cycles.
- Expands registered Python macros recursively, so one macro may be implemented in terms of another.
- Auto-discovers modular Python macros from `macros/`.
- Includes assignment, unconditional jump, addition, truncated subtraction and multiplication macros.
- Allocates fresh generated `Z` variables and labels without colliding with the source program.
- Provides syntax checking, expanded listings, execution traces and configurable step limits.
- Reports duplicate and undefined labels while preserving L execution semantics.
- Implements the numeric encoding used by the UA reference platform through `encoder.py` and `--encode`, while avoiding accidental construction of impractically huge whole-program integers.
- Uses only the Python standard library.

## Primitive language

Variables contain non-negative integers.

- `X1`, `X2`, ... are input variables.
- `Z1`, `Z2`, ... are auxiliary variables.
- `Y` is the output variable.
- `X` and `Z` are accepted as aliases for `X1` and `Z1`.

`X0` and `Z0` are invalid.

| Instruction | Meaning |
| --- | --- |
| `V++` | Increment `V`. |
| `V--` | Decrement `V`; zero remains zero. |
| `V==` | No operation. |
| `IF V != 0 GOTO L` | Jump to `L` when `V` is non-zero. |

Execution ends after the final instruction. A taken jump to an undefined label also terminates the program, matching the semantics used in the notes/reference platform.

Labels are case-insensitive and may be written in either form:

```text
A1: Y++
(A1) Y++
```

A standalone label is also valid:

```text
A1:
Y++
```

Comments may begin with `#` or `//`.

## Registered macros

Python macro modules live under `macros/` and are discovered automatically.

Current macro syntax includes:

```text
GOTO A1
Y <- X1
Y <- X1 + X2
Y <- X1 - X2
Y <- X1 * X2
```

Subtraction is truncated over the natural numbers:

```text
2 - 5 = 0
```

Macro operands are preserved unless the source expression itself writes to one of them. Expansions use fresh internal variables and labels, so constructs such as `X1 <- X1 + X2` are safe.

Registered macros are expanded **recursively**. A new macro may therefore return another registered macro instruction instead of having to reproduce all primitive implementation details itself.

To add a new macro, create another `.py` file inside `macros/` and register it with `@macro(...)`. No central list has to be edited.

## UA-style source macros

The interpreter also understands macros defined directly in a `.l` program, compatible with the macro system in `jcac5-ua/Plataforma-de-pruebas-para-Teoria-de-la-Computacion`.

Example:

```text
MACRO SALTO
W1++
IF W1 != 0 GOTO T1
END

CALL SALTO A1
Y++
A1: Y++
```

Inside a source macro:

| Token | Meaning |
| --- | --- |
| `T1`, `T2`, ... | First, second, ... argument supplied by `CALL`. |
| `W1`, `W2`, ... | Fresh auxiliary `Z` variable local to that invocation. |
| `G1`, `G2`, ... | Fresh local label for that invocation. |
| `F` | Continuation label immediately after that invocation. |

Source macros may call other source macros:

```text
MACRO OUTER
CALL INNER T1 W1
...
END
```

Each invocation gets independent `Wn`, `Gn` and `F` names. Direct or indirect recursive macro cycles are rejected instead of expanding forever.

The predefined `COPIA`, `SUMA`, `RESTA` and `SALTO` macro bodies from the UA reference repository are covered by the test suite.

## Running programs

```bash
python3 l_interpreter.py PROGRAM [INPUT ...] [OPTIONS]
```

Positional input values initialize `X1`, `X2`, ... in order.

Examples:

```bash
python3 l_interpreter.py identity.l 5
python3 l_interpreter.py sum.l 4 7
python3 l_interpreter.py program.l --check
python3 l_interpreter.py program.l --list --check
python3 l_interpreter.py program.l 5 --trace
python3 l_interpreter.py program.l --encode --check
```

Options:

| Option | Purpose |
| --- | --- |
| `--check` | Expand and validate without executing. |
| `--list` | Print the fully expanded primitive program. |
| `--trace` | Show primitive execution step by step. |
| `--encode` | Print exact instruction encodings and the whole-program code when it is reasonably sized. |
| `--max-steps N` | Override the execution limit (default: `1_000_000`). |

Reaching the step limit does not prove that a program is non-terminating; it may simply require more primitive steps.

## Numeric encoding

`encoder.py` implements the coding scheme used by the reference platform:

- `Y -> 0`
- `X_i -> 1 + 2(i-1)`
- `Z_i -> 2 + 2(i-1)`
- `== -> 0`, `++ -> 1`, `-- -> 2`
- conditionals use `2 + code(target label)`
- instruction triples use the pairing function `2^a(2b+1)-1`
- programs use prime-power encoding minus one

Canonical labels use the `A1, B1, C1, D1, S1, A2, ...` sequence. Descriptive/generated labels are mapped to free canonical labels for encoding; canonical labels already written in the source are preserved.

Gödel-style whole-program integers grow extremely quickly. `--encode` always reports the exact instruction codes, but skips materializing the final prime-power integer when its estimated size exceeds a safe threshold. `encoder.encode_program_number(...)` remains available when an exact huge integer is explicitly required.

## Project structure

```text
L_interpreter/
├── l_interpreter.py
├── encoder.py
├── macros/
│   ├── __init__.py
│   ├── registry.py
│   ├── addition.py
│   ├── assignment.py
│   ├── goto.py
│   ├── multiplication.py
│   └── subtraction.py
├── tests/
│   ├── test_encoder.py
│   └── test_interpreter.py
└── doc/
    └── Tema02.pdf
```

## Tests

Run the standard-library test suite with:

```bash
python3 -m unittest discover -s tests -v
```

The tests cover primitive semantics, label compatibility, source macros, nested calls, `F` continuation handling, recursive-expansion protection, subtraction, reference-platform macro compatibility and numeric encoding.
