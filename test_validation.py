import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import log_validation


class LogValidationTests(unittest.TestCase):
    def test_valid_error_log_with_traceable_identifier(self):
        is_valid, note = log_validation._validate('ERROR', 'timeout calling billing-api req_id=8f21')
        self.assertTrue(is_valid)
        self.assertIsNone(note)

    def test_invalid_error_log_without_identifier(self):
        is_valid, note = log_validation._validate('ERROR', 'error occurred')
        self.assertFalse(is_valid)
        self.assertEqual(note, 'error log lacks a traceable identifier')

    def test_invalid_truncated_message(self):
        is_valid, note = log_validation._validate('WARNING', 'service degraded...')
        self.assertFalse(is_valid)
        self.assertEqual(note, 'empty or truncated message')

    def test_known_levels_are_accepted(self):
        valid_cases = {
            'INFO': 'sample message',
            'WARNING': 'sample message',
            'ERROR': 'timeout calling billing-api req_id=abc123',
            'CRITICAL': 'OutOfMemoryError in worker-node-1',
            'DEBUG': 'sample message',
        }

        for level, message in valid_cases.items():
            is_valid, note = log_validation._validate(level, message)
            self.assertTrue(is_valid, f'{level} should be valid with a realistic message')
            self.assertIsNone(note)


if __name__ == '__main__':
    unittest.main()
