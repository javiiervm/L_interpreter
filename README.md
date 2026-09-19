# L Interpreter

A Python command-line interpreter for **L**, a minimal language used to study computability and partial functions. Based on the [course notes on L-computable functions](doc/Tema02.pdf), this project turns formal instruction semantics into an executable tool for validating programs and inspecting state transitions.

The implementation demonstrates language parsing, explicit state management, control-flow execution, and CLI design using only the Python standard library.

**Capabilities**

- Parses and executes all four primitive L instructions.
- Supports variable assignment and unconditional jumps as built-in macro notation.
- Provides syntax checking, normalized program listings, and step-by-step execution traces.
- Reports duplicate and undefined labels while preserving their legal execution semantics.
- Applies a configurable instruction limit to bound execution when exploring potentially non-terminating programs.

**Quick start**

Requires Python 3.7 or later. No third-party packages are needed. Run these commands from the repository root:

```bash
# Execute the identity function: f(x) = x
python3 l_interpreter.py programs/identity.l 5

# Inspect each instruction and the resulting variable state
python3 l_interpreter.py programs/identity.l 5 --trace

# Validate syntax and display the normalized program without executing it
python3 l_interpreter.py programs/identity.l --check --list

# Run the equivalent program using assignment notation
python3 l_interpreter.py programs/identity_macro.l 5
```

The first command prints the following result, alongside a diagnostic about the example's intentionally undefined label `S`:

```text
Program terminated after 17 step(s).
Y = 5
```

**Language reference**

Variables hold non-negative integers. Positional inputs initialize `X1`, `X2`, and so on; local variables (`Z1`, `Z2`, …), omitted inputs, and the output variable `Y` start at zero. `X` and `Z` are aliases for `X1` and `Z1`.

| Instruction | Behavior |
| --- | --- |
| `V++` | Increment `V` by one. |
| `V--` | Decrement `V`, leaving zero unchanged. |
| `V==` | Advance without changing the state. |
| `IF V != 0 GOTO A` | Jump to label `A` when `V` is nonzero. |
| `GOTO A` | Jump unconditionally; built-in macro notation. |
| `V <- W` | Copy the value of `W` into `V`; built-in macro notation. |

Labels prefix instructions, for example `(A) Y++`. Keywords, variables, and labels are case-insensitive. The interpreter also accepts Unicode `≠` and `←`, blank lines, and comments beginning with `#` or `//`.

Execution terminates when it passes the final instruction or takes a jump to an undefined label. If a label appears more than once, jumps target its first occurrence. On termination, `Y` contains the program's result.

For example, the included [assignment-based identity program](programs/identity_macro.l) consists of:

```text
# f(x) = x
Y <- X1
```

The [primitive identity program](programs/identity.l) computes the same function using increment, decrement, and conditional jumps.

**Command-line options**

```text
python3 l_interpreter.py PROGRAM [INPUT ...] [OPTIONS]
```

| Option | Purpose |
| --- | --- |
| `--check` | Parse and validate without execution. |
| `--list` | Print normalized instructions before execution; combine with `--check` to inspect only. |
| `--trace` | Show executed instructions, actions, and variable states. |
| `--max-steps N` | Set a positive execution limit; defaults to `100000`. |
| `--help` | Display usage and syntax examples. |

Reaching the step limit does not prove that a program runs forever: it may require more instructions to finish. Exit codes are `0` for successful validation or termination, `1` for handled source-file, syntax, or runtime errors, and `2` for the execution limit or invalid CLI arguments.

**Implementation and scope**

[l_interpreter.py](l_interpreter.py) separates parsing, execution, diagnostics, and command-line handling. Dataclasses represent instructions, parsed programs, and execution results; a variable-state dictionary and program counter model execution. Parsing retains source line numbers for diagnostics and builds a label lookup table for jumps.

This is an educational interpreter. Assignment and unconditional-jump notation execute directly, with each counting as one interpreter step. General user-defined macro expansion, function-call assignment, and predicate macros from the notes are outside the current implementation. Syntax checking validates accepted source syntax; it does not establish termination or functional correctness.

**Repository contents**

| Path | Contents |
| --- | --- |
| [l_interpreter.py](l_interpreter.py) | Parser, execution engine, diagnostics, and CLI. |
| [programs/](programs/) | Primitive and assignment-based identity examples. |
| [doc/Tema02.pdf](doc/Tema02.pdf) | Spanish course notes defining L syntax, semantics, macros, and computability. |
