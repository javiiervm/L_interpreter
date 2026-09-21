# L Interpreter

A Python command-line interpreter for **L**, a minimal language used to study computability and partial functions. Based on the [course notes on L-computable functions](doc/Tema02.pdf), this project turns formal instruction semantics into an executable tool for validating programs and inspecting state transitions.

The implementation demonstrates language parsing, explicit state management, macro expansion, control-flow execution, and CLI design using only the Python standard library.

**Capabilities**

- Parses and executes all four primitive L instructions.
- Expands variable assignment and unconditional jumps as source-level macros before execution.
- Discovers macro definitions automatically from the modular `macros/` package.
- Provides syntax checking, expanded program listings, and step-by-step execution traces.
- Reports duplicate and undefined labels while preserving their legal execution semantics.
- Applies a configurable primitive-instruction limit to bound execution when exploring potentially non-terminating programs.

**Language reference**

Variables hold non-negative integers. Positional inputs initialize `X1`, `X2`, and so on; local variables (`Z1`, `Z2`, …), omitted inputs, and the output variable `Y` start at zero. `X` and `Z` are aliases for `X1` and `Z1`.

| Instruction | Behavior |
| --- | --- |
| `V++` | Increment `V` by one. |
| `V--` | Decrement `V`, leaving zero unchanged. |
| `V==` | Advance without changing the state. |
| `IF V != 0 GOTO A` | Jump to label `A` when `V` is nonzero. |
| `GOTO A` | Built-in macro for an unconditional jump. |
| `V <- W` | Built-in macro that copies `W` into `V` while preserving `W`. |

Labels prefix instructions, for example `(A) Y++`. Keywords, variables, and labels are case-insensitive. The interpreter also accepts Unicode `≠` and `←`, blank lines, and comments beginning with `#` or `//`.

Execution terminates when it passes the final instruction or takes a jump to an undefined label. If a label appears more than once, jumps target its first occurrence. On termination, `Y` contains the program's result.

**Macro system**

The interpreter runtime only executes the four primitive L operations. Source-level macros are expanded first by the `macros/` package.

```text
macros/
├── __init__.py      # Automatic module discovery
├── registry.py      # Registry and expansion context
├── assignment.py    # V <- W / V ← W
└── goto.py          # GOTO L
```

`macros/__init__.py` automatically imports every non-private `.py` module in the package except `registry.py`. This means a new macro normally requires only one new file; neither `l_interpreter.py` nor `macros/__init__.py` needs to be edited.

Each expansion receives a `MacroExpansionContext` that can allocate fresh `Z` variables and labels without colliding with names already present in the source program.

To add a macro, create a file such as `macros/clear.py`:

```python
from .registry import IDENTIFIER_PATTERN, macro


@macro(
    name="CLEAR",
    pattern=rf"\s*CLEAR\s+(?P<var>{IDENTIFIER_PATTERN})\s*",
    syntax="CLEAR V",
)
def expand_clear(match, context):
    variable = match.group("var")
    guard = context.new_variable()
    test = context.new_label("CLEAR_TEST")
    step = context.new_label("CLEAR_STEP")
    done = context.new_label("CLEAR_DONE")

    return (
        f"{guard}++",
        f"({test}) IF {variable} != 0 GOTO {step}",
        f"IF {guard} != 0 GOTO {done}",
        f"({step}) {variable}--",
        f"IF {guard} != 0 GOTO {test}",
        f"({done}) {variable}==",
    )
```

Expansion functions must return one or more **primitive L instructions**. Registered macro syntax is picked up automatically by the parser and displayed by `--help`. Duplicate macro names are rejected during registration.

**Command-line options**

```text
python3 l_interpreter.py PROGRAM [INPUT ...] [OPTIONS]
```

| Option | Purpose |
| --- | --- |
| `--check` | Expand macros, parse, and validate without execution. |
| `--list` | Print the fully expanded primitive program before execution; combine with `--check` to inspect only. |
| `--trace` | Show primitive instructions, actions, and variable states step by step. |
| `--max-steps N` | Set a positive primitive-instruction limit; defaults to `100000`. |
| `--help` | Display usage, primitive syntax, and registered macros. |

Because macros are genuine source expansions, one macro instruction can execute as several primitive steps. Reaching the step limit does not prove that a program runs forever: it may require more instructions to finish.

**Implementation and scope**

[l_interpreter.py](l_interpreter.py) contains the primitive parser, execution engine, diagnostics, and command-line handling. [`macros/registry.py`](macros/registry.py) provides the reusable macro infrastructure, while each concrete macro is isolated in its own module.

This is an educational interpreter. The macro package is extensible in Python, but `.l` source files do not currently define their own macro bodies. Function-call assignment and predicate macros from later parts of the notes can be added as separate files under `macros/` when their intended notation and expansion rules are needed.
