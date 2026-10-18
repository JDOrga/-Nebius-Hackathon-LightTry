"""Host-network web stays loopback-only unless explicitly configured otherwise."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service import parser


class ServiceBindOptionsTests(unittest.TestCase):
    def test_default_preserves_existing_bridge_binding(self):
        options=parser().parse_args([])
        self.assertEqual((options.listen_host,options.listen_port),('0.0.0.0',8080))

    def test_host_network_binding_is_explicit_loopback(self):
        options=parser().parse_args(['--listen-host','127.0.0.1','--listen-port','8081'])
        self.assertEqual((options.listen_host,options.listen_port),('127.0.0.1',8081))

    def test_invalid_bindings_fail(self):
        for args in (['--listen-host','::'],['--listen-port','80'],['--listen-port','bad']):
            with self.subTest(args=args),self.assertRaises(SystemExit):
                parser().parse_args(args)
