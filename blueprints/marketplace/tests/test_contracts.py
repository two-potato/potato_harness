"""R1 contract validation, including negative security and compatibility cases."""
import copy
import json
from pathlib import Path
import unittest

import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT/'schemas/marketplace.factory.v1.schema.json').read_text())
EVENT = json.loads((ROOT/'schemas/event-envelope.v1.schema.json').read_text())
BASE = yaml.safe_load((ROOT/'examples/marketplace.factory.example.yaml').read_text())


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Draft202012Validator.check_schema(SCHEMA)
        Draft202012Validator.check_schema(EVENT)
        cls.validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
        cls.events = Draft202012Validator(EVENT, format_checker=FormatChecker())

    def test_valid_local_dev_manifest(self):
        self.validator.validate(BASE)
        self.assertEqual(set(BASE['services']), {'search','notifications','recommendations','moderation','analytics'})

    def _reject(self, mutate):
        bad=copy.deepcopy(BASE)
        mutate(bad)
        with self.assertRaises(ValidationError):
            self.validator.validate(bad)

    def test_mandatory_services_cannot_be_disabled(self):
        for service in BASE['services']:
            with self.subTest(service=service):
                self._reject(lambda m: m['services'][service].update(enabled=False))
                self._reject(lambda m: m['services'].pop(service))

    def test_no_unbounded_or_untrusted_gateway(self):
        self._reject(lambda m: m['gateway'].update(provider='none'))
        self._reject(lambda m: m['gateway'].update(public_admin_api=True))
        self._reject(lambda m: m['deployment'].update(publish_internal_ports=True))

    def test_country_currency_and_psp_require_explicit_safe_selection(self):
        self._reject(lambda m: m['market'].update(country='ZZ'))
        self._reject(lambda m: m['market'].update(currency='RUB; DROP DATABASE'))
        self._reject(lambda m: m['market'].update(currency='USD'))
        self._reject(lambda m: m['market']['country_pack'].update(production_payments_allowed=True))
        self._reject(lambda m: m['payments'].update(provider='unknown_live_psp'))
        self._reject(lambda m: m['payments'].update(mode='production'))
        self._reject(lambda m: m['payments']['required_capabilities'].remove('seller_payouts'))

    def test_no_floating_images(self):
        self._reject(lambda m: m['deployment']['images'].update(api='django:latest'))
        self._reject(lambda m: m['deployment']['images'].update(api='registry.example.invalid/api:1.0'))

    def test_project_and_blueprint_identity(self):
        self._reject(lambda m: m['project'].update(slug='../escape'))
        self._reject(lambda m: m['project'].update(isolation='shared_db'))
        self._reject(lambda m: m['blueprint'].update(source_sha='main'))
        self._reject(lambda m: m['services'].update(hidden={'enabled':True}))

    def test_yaml_security_and_no_secret_fields(self):
        self._reject(lambda m: m.update(api_secret='do-not-put-secrets-in-manifest'))
        self._reject(lambda m: m['payments'].update(secret='never'))

    def test_event_envelope_and_stale_moderation_are_revision_bound(self):
        valid={'event_id':'0462bc24-4a39-4df0-a086-6170ea164a3e',
               'event_type':'moderation.verdict.v1','schema_version':'marketplace.event/v1',
               'occurred_at':'2026-11-11T11:00:00Z','project_id':'demo-market-kz',
               'aggregate_id':'listing-1','aggregate_version':2,
               'correlation_id':'d8a77968-c20c-4b24-93bc-f5a7a5fe55da',
               'payload':{'listing_id':'listing-1','content_sha256':'sha256:'+'b'*64,
                          'verdict':'APPROVE','decision_id':'d8a77968-c20c-4b24-93bc-f5a7a5fe55da',
                          'policy_digest':'sha256:'+'a'*64,'issuer_id':'trusted-moderator'}}
        self.events.validate(valid)
        for mutate in [lambda e: e['payload'].pop('content_sha256'),
                       lambda e: e['payload'].pop('policy_digest'),
                       lambda e: e.update(aggregate_version=0),
                       lambda e: e['payload'].update(customer_email='private@invalid'),
                       lambda e: e.update(event_type='customer.pii.export')]:
            bad=copy.deepcopy(valid);mutate(bad)
            with self.assertRaises(ValidationError):self.events.validate(bad)

    def test_openapi_and_asyncapi_contracts_parse(self):
        names={'search','notifications','recommendations','moderation','analytics'}
        specs={p.stem for p in (ROOT/'contracts/openapi').glob('*.yaml')}
        self.assertEqual(names,specs)
        for name in names:
            doc=yaml.safe_load((ROOT/'contracts/openapi'/f'{name}.yaml').read_text())
            self.assertEqual(doc['openapi'],'3.1.0')
            self.assertTrue(doc['paths'])
            self.assertTrue(doc['components']['securitySchemes'])
        asyncapi=yaml.safe_load((ROOT/'contracts/asyncapi/marketplace-events.v1.yaml').read_text())
        self.assertEqual(asyncapi['asyncapi'],'3.0.0')
        self.assertIn('listingPublished',asyncapi['channels'])


if __name__=='__main__':unittest.main()
