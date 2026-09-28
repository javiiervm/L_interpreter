import unittest

from macros import macro
from l_interpreter import LSyntaxError, execute, get_value, parse_source


@macro(name="TEST_COMPOSE", pattern=r"\s*TEST_COMPOSE\s*", syntax="TEST_COMPOSE")
def _expand_test_compose(match, context):
    # Deliberately expands to another registered macro.
    return ("Y <- X1",)

REFERENCE_MACROS = """
MACRO COPIA
IF T2 != 0 GOTO G4
W1 ++
IF W1 != 0 GOTO G5
G4: T2 --
IF T2 != 0 GOTO G4
G5: IF T1 != 0 GOTO G2
W2 ++
IF W1 != 0 GOTO F
G2: T1 --
T2 ++
W3 ++
IF T1 != 0 GOTO G2
G3: W3 --
T1 ++
IF W3 != 0 GOTO G3
END

MACRO SALTO
W1 ++
IF W1 != 0 GOTO T1
END

MACRO SUMA
IF T3 != 0 GOTO G1
CALL SALTO G2
G1: T3 --
IF T3 != 0 GOTO G1
G2: CALL COPIA T2 W2
CALL COPIA T1 T3
IF T2 != 0 GOTO G3
CALL SALTO G4
G3: T3 ++
T2 --
IF T2 != 0 GOTO G3
G4: CALL COPIA W2 T2
END

MACRO RESTA
CALL COPIA T1 T3
CALL COPIA T2 W1
IF T2 != 0 GOTO G1
CALL SALTO F
G1: W1 --
T3 --
IF W1 != 0 GOTO G1
END
"""

class InterpreterTests(unittest.TestCase):
    def run_program(self, source, *inputs, max_steps=1_000_000):
        program = parse_source(source)
        result = execute(program, inputs, max_steps=max_steps)
        self.assertFalse(result.step_limit_reached)
        return result

    def test_colon_parenthesized_and_standalone_labels(self):
        source = """
        A1:
        (ALIAS) Y++
        X1--
        IF X1 != 0 GOTO ALIAS
        """
        result = self.run_program(source, 2)
        self.assertEqual(get_value(result.state, "Y"), 2)

    def test_terminal_standalone_label(self):
        source = """
        Y++
        END_LABEL:
        IF Y != 0 GOTO END_LABEL
        """
        # END_LABEL prefixes the IF because it is not at EOF yet.
        # So use an explicitly terminal label instead.
        terminal = parse_source("Y++\nIF Y != 0 GOTO FIN\nFIN:\n")
        result = execute(terminal, [])
        self.assertTrue(result.terminated)
        self.assertEqual(result.state["Y"], 1)

    def test_undefined_label_terminates(self):
        result = self.run_program("Y++\nIF Y != 0 GOTO MISSING\nY++")
        self.assertEqual(result.state["Y"], 1)

    def test_x0_and_z0_are_rejected(self):
        with self.assertRaises(LSyntaxError):
            parse_source("X0++")
        with self.assertRaises(LSyntaxError):
            parse_source("Z0++")

    def test_registered_macros_expand_recursively(self):
        result = self.run_program("TEST_COMPOSE", 6)
        self.assertEqual(result.state["Y"], 6)

    def test_python_subtraction_macro(self):
        result = self.run_program("Y <- X1 - X2", 7, 3)
        self.assertEqual(result.state["Y"], 4)
        self.assertEqual(result.state["X1"], 7)
        self.assertEqual(result.state["X2"], 3)

        result = self.run_program("Y <- X1 - X2", 2, 5)
        self.assertEqual(result.state["Y"], 0)

    def test_subtraction_is_safe_when_reexecuted_in_a_loop(self):
        source = """
        Y <- X1
        LOOP: Y <- Y - X2
        X3--
        IF X3 != 0 GOTO LOOP
        """
        result = self.run_program(source, 5, 1, 2)
        self.assertEqual(result.state["Y"], 3)

    def test_source_macro_f_continuation(self):
        source = """
        MACRO SKIP
        W1++
        IF W1 != 0 GOTO F
        T1++
        END
        CALL SKIP Y
        Y++
        """
        result = self.run_program(source)
        self.assertEqual(result.state["Y"], 1)

    def test_recursive_source_macro_is_rejected(self):
        source = """
        MACRO LOOP
        CALL LOOP T1
        END
        CALL LOOP Y
        """
        with self.assertRaises(LSyntaxError):
            parse_source(source)

    def test_reference_copy_macro(self):
        result = self.run_program(REFERENCE_MACROS + "\nCALL COPIA X1 Y\n", 4)
        self.assertEqual(result.state["Y"], 4)
        self.assertEqual(result.state["X1"], 4)

    def test_reference_sum_macro_with_nested_calls(self):
        result = self.run_program(REFERENCE_MACROS + "\nCALL SUMA X1 X2 Y\n", 2, 3)
        self.assertEqual(result.state["Y"], 5)
        self.assertEqual(result.state["X1"], 2)
        self.assertEqual(result.state["X2"], 3)

    def test_reference_subtraction_macro(self):
        result = self.run_program(REFERENCE_MACROS + "\nCALL RESTA X1 X2 Y\n", 5, 2)
        self.assertEqual(result.state["Y"], 3)
        self.assertEqual(result.state["X1"], 5)
        self.assertEqual(result.state["X2"], 2)

if __name__ == "__main__":
    unittest.main()
