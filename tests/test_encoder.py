import unittest
from encoder import encode_program, label_code, num_pair, variable_code
from l_interpreter import parse_source

class EncoderTests(unittest.TestCase):
    def test_reference_codes(self):
        self.assertEqual(variable_code("Y"), 0)
        self.assertEqual(variable_code("X1"), 1)
        self.assertEqual(variable_code("Z1"), 2)
        self.assertEqual(variable_code("X2"), 3)
        self.assertEqual(label_code("A1"), 1)
        self.assertEqual(label_code("S1"), 5)
        self.assertEqual(label_code("A2"), 6)

    def test_single_increment_program_code(self):
        encoding = encode_program(parse_source("A1: X1++"))
        expected_instruction = num_pair(1, num_pair(1, 1))
        self.assertEqual(expected_instruction, 21)
        self.assertEqual(encoding.instructions[0].code, 21)
        self.assertEqual(encoding.program_code, 2**21 - 1)

    def test_descriptive_labels_are_canonicalized(self):
        program = parse_source("LOOP: Y++\nIF Y != 0 GOTO LOOP")
        encoding = encode_program(program)
        self.assertEqual(encoding.label_mapping["LOOP"], "A1")

    def test_existing_canonical_labels_are_preserved(self):
        program = parse_source("LOOP: Y++\nA1: Y==\nIF Y != 0 GOTO A1")
        encoding = encode_program(program)
        self.assertEqual(encoding.label_mapping["A1"], "A1")
        self.assertNotEqual(encoding.label_mapping["LOOP"], "A1")

if __name__ == "__main__":
    unittest.main()
