"""Contract-only marketplace CLI tests; never invoke models or Docker."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'tools/marketplace.py'


class MarketplaceEntrypointTests(unittest.TestCase):
    def invoke(self,*args):
        return subprocess.run([sys.executable,str(SCRIPT),*map(str,args)],
                              cwd=ROOT,capture_output=True,text=True)

    def test_status_reports_no_runtime(self):
        r=self.invoke('status')
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        status=json.loads(r.stdout)
        self.assertFalse(status['marketplace_generator_ready'])
        self.assertFalse(status['sandbox_authorized'])
        self.assertCountEqual(status['required_services'],
                              ['search','notifications','recommendations','moderation','analytics'])

    def test_validate_keeps_execution_denied(self):
        r=self.invoke('validate',ROOT/'blueprints/marketplace/examples/marketplace.factory.example.yaml')
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        self.assertFalse(json.loads(r.stdout)['execution_authorized'])

    def test_init_creates_clean_independent_git_without_marketplace_claim(self):
        with tempfile.TemporaryDirectory() as parent:
            output=Path(parent)/'independent-market'
            r=self.invoke('init','independent-market','--output',output)
            self.assertEqual(r.returncode,0,r.stderr+r.stdout)
            status=json.loads(r.stdout)
            self.assertFalse(status['marketplace_running'])
            self.assertFalse(status['production_approved'])
            self.assertTrue((output/'.git').is_dir())
            self.assertIn('slug: independent-market',(output/'marketplace.factory.yaml').read_text())
            head=subprocess.run(['git','-C',str(output),'rev-parse','HEAD'],
                                capture_output=True,text=True,check=True)
            self.assertEqual(len(head.stdout.strip()),40)
            self.assertNotEqual(self.invoke('init','independent-market','--output',output).returncode,0)

    def test_refuses_in_repo_output_and_traversal_slug(self):
        with tempfile.TemporaryDirectory() as parent:
            self.assertEqual(self.invoke('init','../../oops','--output',Path(parent)/'oops').returncode,2)
        self.assertEqual(self.invoke('init','good-market','--output',ROOT/'forbidden-marketplace').returncode,2)
        self.assertFalse((ROOT/'forbidden-marketplace').exists())

    def test_symlink_output_parent_rejected(self):
        with tempfile.TemporaryDirectory() as parent:
            origin=Path(parent)/'origin';origin.mkdir()
            alias=Path(parent)/'alias';alias.symlink_to(origin,target_is_directory=True)
            r=self.invoke('init','safe-market','--output',alias/'safe-market')
            self.assertEqual(r.returncode,2)
            self.assertFalse((origin/'safe-market').exists())

    def test_root_opencode_profile_denies_untrusted_tools(self):
        config=json.loads((ROOT/'opencode.json').read_text())
        self.assertEqual(config['permission'].get('*'),'deny')
        self.assertIn('AGENTS.md',config['instructions'])
        self.assertEqual(config['share'],'disabled')

    def test_opencode_command_never_embeds_shell_expansion(self):
        template=(ROOT/'.opencode/commands/marketplace.md').read_text()
        self.assertIn('AGENTS.md',template)
        self.assertIn('tools/marketplace.py',template)
        self.assertNotIn('!`',template)
        self.assertNotIn('agent: build',template)


if __name__=='__main__':unittest.main()
