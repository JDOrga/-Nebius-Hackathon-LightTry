"""UTC parse compatibility for PowerShell round-trip timestamps and Python 3.10."""
from datetime import datetime,timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from weights import parse_utc

class PrecisionTests(unittest.TestCase):
    def test_seven_digits_truncate_without_extending_cutoff(self):
        self.assertEqual(parse_utc('2030-01-02T03:04:05.1234567+00:00'),datetime(2030,1,2,3,4,5,123456,tzinfo=timezone.utc))

    def test_fraction_precision_and_z(self):
        for text,microseconds in [('1',100000),('12',120000),('123',123000),('1234',123400),('12345',123450),('123456',123456)]:
            self.assertEqual(parse_utc('2030-01-02T03:04:05.'+text+'Z').microsecond,microseconds)

    def test_explicit_utc_required(self):
        for text in ('2030-01-02T03:04:05','2030-01-02T03:04:05+08:00'):
            with self.assertRaises(ValueError):parse_utc(text)

if __name__=='__main__':unittest.main()
