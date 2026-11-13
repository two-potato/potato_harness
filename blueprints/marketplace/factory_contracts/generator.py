"""R2 development-scaffold generator. Offline, no model/Docker/network execution.

These files are not a full marketplace, deployment, or security approval. The
checked-in templates are local source. A lock records their exact bytes but does
not authenticate the repository publisher or resolve external country packs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "r2"
MAX_TEMPLATE_FILES = 96
MAX_TEMPLATE_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 1024 * 1024


class GenerationError(ValueError):
    """Template is unavailable or unsafe; do not trust generated output."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _plain(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def template_contents() -> dict[str, bytes]:
    """Enumerate bounded, normal tracked-file candidates; never follow symlinks."""
    if not TEMPLATES.is_dir() or TEMPLATES.is_symlink():
        raise GenerationError("R2 templates unavailable")
    files: dict[str, bytes] = {}
    total = 0
    for path in sorted(TEMPLATES.rglob("*")):
        relative = path.relative_to(TEMPLATES)
        parts = relative.parts
        if (not parts or any(p in ("", ".", "..", ".git", "__pycache__") for p in parts)
                or any(p.startswith(".") and p not in (".env.example", ".gitignore") for p in parts)):
            raise GenerationError("Unsafe generator template path")
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise GenerationError("Template must be a regular single-link file")
        if info.st_size > MAX_TEMPLATE_BYTES:
            raise GenerationError("Template exceeds file bound")
        data = path.read_bytes()
        total += len(data)
        if total > MAX_TOTAL_BYTES or len(files) >= MAX_TEMPLATE_FILES:
            raise GenerationError("Template bundle exceeds bounds")
        files[relative.as_posix()] = data
    essential = {"backend/manage.py", "backend/config/settings.py", "backend/catalog/models.py",
                 "backend/catalog/migrations/0001_initial.py", "frontend/package.json",
                 "frontend/app/page.tsx", ".env.example", ".gitignore"}
    if not essential.issubset(files):
        raise GenerationError("Incomplete R2 template set")
    return files


def generated_files(manifest_text: bytes, manifest: dict) -> dict[str, bytes]:
    """Build the same project bytes for the same manifest and template revision."""
    if manifest.get("schema_version") != "marketplace.factory/v1":
        raise GenerationError("Unsupported manifest version")
    slug = manifest["project"]["slug"]
    if (manifest["market"]["country"] != "KZ"
            or manifest["market"]["currency"] != "KZT"):
        raise GenerationError("R2 development scaffold currently supports KZ/KZT only")
    if (manifest["payments"]["provider"] != "fake_psp"
            or manifest["payments"]["mode"] != "sandbox"
            or manifest["market"]["country_pack"]["production_payments_allowed"] is not False):
        raise GenerationError("Only unverified sandbox marketplace generation permitted")
    files = template_contents()
    hashes = {name: _sha(value) for name, value in sorted(files.items())}
    source_digest = _sha(_plain(hashes))
    project: dict[str, bytes] = dict(files)
    project["marketplace.factory.yaml"] = manifest_text
    project["blueprint.lock"] = _plain({
        "schema_version": "potato.blueprint.lock/v1",
        "generator_stage": "R2_DEV_SCAFFOLD",
        "project_slug": slug,
        "manifest_sha256": "sha256:" + _sha(manifest_text),
        "templates_sha256": "sha256:" + source_digest,
        "template_files": {name: "sha256:" + value for name, value in hashes.items()},
        "source_repository_authenticated": False,
        "country_pack_verified": False,
        "payments": "fake_psp_sandbox_only",
        "production_approved": False,
        "runtime_verified": False,
    })
    project["README.md"] = (f"# {slug}\n\n"
        "Potato Marketplace **R2 development scaffold**. This generates actual Django/DRF "
        "catalog source and a Next.js storefront source, not a deployed or production-ready marketplace.\n\n"
        "## Local developer setup\n\n"
        "Requires Python 3.13+, Node.js 22+, local PostgreSQL and reviewed package installs. "
        "Do not run untrusted source until host isolation/admission is verified.\n\n"
        "```sh\n"
        "cd backend\n"
        "python3 -m venv .venv\n"
        ".venv/bin/pip install -r requirements.txt\n"
        "# Set DJANGO_SECRET_KEY (32+ characters), PG* environment variables\n"
        ".venv/bin/python manage.py migrate\n"
        ".venv/bin/python manage.py test catalog\n"
        ".venv/bin/python manage.py runserver 127.0.0.1:8000\n"
        "# separate terminal:\n"
        "cd ../frontend\n"
        "npm install --ignore-scripts\n"
        "npm run typecheck\n"
        "npm run dev\n"
        "```\n\n"
        "Security: only owner-scoped writes, revision-gated seller submissions and "
        "published-only reads are scaffolded. No autonomous moderation approval, "
        "payment settlement, five running services, Kong, Swarm or integrations. "
        "Generated code MUST pass independent review and actual integration tests "
        "before any trusted agent executes it.\n\n"
        "`blueprint.lock` records template bytes reproducibly; it is NOT a signed "
        "release provenance. `marketplace.factory.yaml` is a sandbox fixture.\n").encode()
    project["NEXT_STEPS.md"] = (
        "# Milestones after this R2 development scaffold\n\n"
        "1. Run Django checks + PostgreSQL migrations + seller isolation regression tests.\n"
        "2. Build/typecheck Next.js with a locked dependency graph (R2).\n"
        "3. Complete OpenAPI response schemas and deterministic TS clients (#16).\n"
        "4. Complete country pack/PSP compliance and seller moderation service contracts.\n"
        "5. Build Kong/Nginx, Swarm and observability (R3).\n"
        "6. Implement five separate mandatory services and end-to-end evidence (R4–R5).\n"
        "7. Complete authenticated capability grants and protected runner (#17).\n"
    ).encode()
    return project
