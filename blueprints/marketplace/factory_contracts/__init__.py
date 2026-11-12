"""R1 trusted manifest validation. This does not provision or authorize deployment."""

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
MAX_MANIFEST_BYTES = 64 * 1024


class ManifestError(ValueError):
    """Invalid or unsupported project manifest."""


class UniqueKeysLoader(yaml.SafeLoader):
    """Reject YAML duplicate keys instead of silently changing security settings."""


def _unique_mapping(loader, node):
    keys = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in keys:
            raise ManifestError('Duplicate or non-string YAML mapping key')
        keys.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=True)


UniqueKeysLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def validate_manifest(filename: str | Path) -> dict:
    """Validate sandbox-only R1 manifest; never run commands from it."""
    path = Path(filename)
    if path.is_symlink() or not path.is_file():
        raise ManifestError('Manifest must be a regular non-symlink file')
    content = path.read_bytes()
    if not content or len(content) > MAX_MANIFEST_BYTES:
        raise ManifestError('Manifest must be nonempty and <= 64 KiB')
    try:
        data = yaml.load(content.decode('utf-8'), Loader=UniqueKeysLoader)
        if not isinstance(data, dict):
            raise ManifestError('Manifest root must be a mapping')
        schema = json.loads((ROOT/'schemas/marketplace.factory.v1.schema.json').read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
    except (UnicodeError, yaml.YAMLError, json.JSONDecodeError) as error:
        raise ManifestError('Invalid manifest encoding or YAML') from error
    except __import__('jsonschema').ValidationError as error:
        # Never print user-supplied data from validation exceptions; only the path.
        raise ManifestError('Manifest violates schema at ' + '/'.join(map(str,error.absolute_path))) from error
    return data
