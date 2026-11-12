"""Validate a local marketplace.factory/v1 manifest without executing it."""

import argparse
import json

from . import ManifestError, validate_manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    args = parser.parse_args(argv)
    try:
        data = validate_manifest(args.manifest)
        result = {'status': 'PASS', 'schema_version': data['schema_version'],
                  'project': data['project']['slug'], 'execution_authorized': False,
                  'production_approved': False}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ManifestError, OSError) as error:
        print(json.dumps({'status':'HOLD','reason':str(error)},sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
