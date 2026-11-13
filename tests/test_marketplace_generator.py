"""Offline source-only R2 generator tests. Never executes generated project code."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/marketplace.py"
BLUEPRINT = ROOT / "blueprints/marketplace"
sys.path.insert(0, str(BLUEPRINT))
from factory_contracts.generator import GenerationError, generated_files, template_contents


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GeneratorTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)], cwd=ROOT,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=25)

    def test_generate_independent_git_and_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)/"sample-market"
            result = self.invoke("generate", "sample-market", "--output", dest)
            self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
            data=json.loads(result.stdout)
            self.assertEqual(data["status"], "R2_DEV_SCAFFOLD")
            self.assertFalse(data["marketplace_running"])
            self.assertFalse(data["production_approved"])
            self.assertGreaterEqual(data["files_generated"], 20)
            self.assertTrue((dest/".git").is_dir())
            self.assertTrue((dest/"backend/catalog/models.py").is_file())
            self.assertTrue((dest/"backend/catalog/migrations/0001_initial.py").is_file())
            self.assertTrue((dest/"frontend/app/page.tsx").is_file())
            lock = json.loads((dest/"blueprint.lock").read_text())
            self.assertEqual(lock["project_slug"], "sample-market")
            self.assertEqual(lock["schema_version"], "potato.blueprint.lock/v1")
            self.assertFalse(lock["production_approved"])
            self.assertFalse(lock["source_repository_authenticated"])
            self.assertEqual(lock["manifest_sha256"], "sha256:"+sha((dest/"marketplace.factory.yaml").read_bytes()))
            self.assertEqual(lock["template_files"]["backend/manage.py"], "sha256:"+sha((dest/"backend/manage.py").read_bytes()))
            self.assertEqual(self.invoke("generate", "sample-market", "--output", dest).returncode, 2)

    def test_reproducible_tree_and_git_head(self):
        with tempfile.TemporaryDirectory() as parent:
            tree=[]
            heads=[]
            for dirname in ("a", "b"):
                dest=Path(parent)/dirname
                out=self.invoke("generate", "same-market", "--output", dest)
                self.assertEqual(out.returncode,0,out.stdout+out.stderr)
                tree.append({p.relative_to(dest).as_posix():sha(p.read_bytes()) for p in dest.rglob("*")
                             if p.is_file() and ".git" not in p.relative_to(dest).parts})
                heads.append(subprocess.check_output(["git", "-C", str(dest), "rev-parse", "HEAD"],text=True).strip())
            self.assertEqual(tree[0],tree[1]);self.assertEqual(heads[0],heads[1])

    def test_reject_path_traversal_overwrite_and_alias(self):
        with tempfile.TemporaryDirectory() as parent:
            root=Path(parent);existing=root/"existing";existing.mkdir()
            (existing/"protected").write_text("never replace")
            self.assertEqual(self.invoke("generate", "good-market", "--output", existing).returncode,2)
            self.assertEqual((existing/"protected").read_text(),"never replace")
            self.assertEqual(self.invoke("generate", "../../bad", "--output", root/"bad").returncode,2)
            sub=root/"sub";sub.mkdir()
            self.assertEqual(self.invoke("generate", "good-market", "--output",sub/".."/"bad").returncode,2)
            link=root/"link";link.symlink_to(existing,target_is_directory=True)
            self.assertEqual(self.invoke("generate", "good-market", "--output",link/"child").returncode,2)
            self.assertFalse((existing/"child").exists())
        self.assertEqual(self.invoke("generate", "good-market", "--output", ROOT/"rogue").returncode,2)

    def test_custom_manifest_matches_slug_and_rejects_prod_psp(self):
        source=(BLUEPRINT/"examples/marketplace.factory.example.yaml").read_text()
        with tempfile.TemporaryDirectory() as parent:
            manifest=Path(parent)/"sample.yaml"
            manifest.write_text(source.replace("demo-market-kz", "sample-market"))
            output=Path(parent)/"a"
            self.assertEqual(self.invoke("generate", "bad-market", "--manifest",manifest,"--output",output).returncode,2)
            self.assertFalse(output.exists())
            self.assertEqual(self.invoke("generate", "sample-market", "--manifest",manifest,"--output",output).returncode,0)
            manifest.write_text(source.replace("fake_psp", "real_psp"))
            self.assertEqual(self.invoke("generate", "demo-market-kz", "--manifest",manifest,"--output",Path(parent)/"b").returncode,2)

    def test_generated_python_syntax_and_json(self):
        files=template_contents()
        self.assertGreaterEqual(len(files),20)
        for name,data in files.items():
            if name.endswith(".py"):
                ast.parse(data.decode(),filename=name)
            if name.endswith(".json"):
                json.loads(data)
        self.assertIn(b"SellerWritePermission", files["backend/catalog/views.py"])
        self.assertIn(b"expected_revision", files["backend/catalog/views.py"])
        self.assertIn(b"name=\"seller\"", files["backend/catalog/permissions.py"])
        self.assertIn(b"django.db.backends.postgresql", files["backend/config/settings.py"])
        for required in ("backend/catalog/auth_views.py",
                         "backend/catalog/moderation.py",
                         "backend/catalog/migrations/0002_moderation_decisions.py",
                         "frontend/app/seller/page.tsx",
                         "frontend/app/moderation/page.tsx",
                         "frontend/lib/session.ts"):
            self.assertIn(required, files)
        self.assertIn(b"CSRF_TRUSTED_ORIGINS",files["backend/config/settings.py"])
        self.assertIn(b"ModerationDecide",files["backend/catalog/views.py"])

    def test_symlink_template_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)
            (base/"target").write_text("untrusted")
            (base/"alias").symlink_to(base/"target")
            with patch("factory_contracts.generator.TEMPLATES", base):
                with self.assertRaises(GenerationError):template_contents()

    def test_legacy_init_remains_contract_only(self):
        with tempfile.TemporaryDirectory() as root:
            dest=Path(root)/"legacy-market"
            r=self.invoke("init", "legacy-market", "--output",dest)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertTrue((dest/".git").exists())
            self.assertFalse((dest/"backend").exists())
            self.assertFalse(json.loads(r.stdout)["marketplace_running"])


if __name__=="__main__":
    unittest.main()
