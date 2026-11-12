import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from factory_contracts import ManifestError, validate_manifest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT/'examples/marketplace.factory.example.yaml'


class ValidatorCliTests(unittest.TestCase):
    def test_cli_accepts_sandbox_manifest_without_authorizing_execution(self):
        result = subprocess.run([sys.executable,'-m','factory_contracts',str(EXAMPLE)],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads(result.stdout)
        self.assertEqual(report['status'],'PASS')
        self.assertFalse(report['execution_authorized'])
        self.assertFalse(report['production_approved'])

    def test_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'manifest.yaml'
            file.write_text(EXAMPLE.read_text()+'\nproject: {slug: malicious}\n')
            with self.assertRaises(ManifestError):validate_manifest(file)

    def test_symlink_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'linked.yaml';path.symlink_to(EXAMPLE)
            with self.assertRaises(ManifestError):validate_manifest(path)

    def test_size_bound_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'large.yaml';path.write_bytes(b'x'*65537)
            with self.assertRaises(ManifestError):validate_manifest(path)

    def test_cli_rejects_production_psp_without_leaking_value(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.yaml'
            path.write_text(EXAMPLE.read_text().replace('provider: fake_psp','provider: live_secret_payment_psp'))
            result=subprocess.run([sys.executable,'-m','factory_contracts',str(path)],
                                  cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertNotIn('live_secret_payment_psp',result.stdout)
            self.assertEqual(json.loads(result.stdout)['status'],'HOLD')
