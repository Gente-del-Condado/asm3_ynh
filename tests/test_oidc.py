"""OIDC protocol validation with genuine RSA signatures and adversarial claims."""
import copy
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'conf'))
import ynh_oidc as oidc
import ynh_auth as auth

import jwt


class TokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key()))
        cls.jwk.update(kid='current', use='sig', alg='RS256')

    def setUp(self):
        self.cfg = {'issuer': 'https://id.example.test/dex', 'client_id': 'asm3',
                    'groups_claim': 'groups', 'allowed_subjects': [], 'allowed_groups': ['staff']}
        self.metadata = {'jwks_uri': self.cfg['issuer'] + '/keys'}
        self.claims = {'iss': self.cfg['issuer'], 'aud': 'asm3', 'sub': 'stable-subject',
                       'exp': int(time.time()) + 300, 'iat': int(time.time()),
                       'nonce': 'transaction-nonce', 'groups': ['staff']}
        self.http = patch.object(oidc, 'request_json', return_value={'keys': [self.jwk]})
        self.http.start()
        self.addCleanup(self.http.stop)

    def token(self, changes=None, remove=None, key=None, headers=None):
        import jwt
        claims = copy.deepcopy(self.claims)
        claims.update(changes or {})
        if remove:
            claims.pop(remove)
        return jwt.encode(claims, key or self.key, algorithm='RS256', headers=headers or {'kid': 'current'})

    def verify(self, token):
        return oidc.verify_token(self.cfg, self.metadata, token, 'transaction-nonce')

    def test_valid_signature_and_allowlist(self):
        self.assertEqual(self.verify(self.token())['sub'], 'stable-subject')

    def test_wrong_signature_rejected(self):
        with self.assertRaises(auth.AccessDenied):
            self.verify(self.token(key=self.other))

    def test_rejects_wrong_issuer_audience_nonce_authorized_party(self):
        for changes in ({'iss': 'https://attacker.test'}, {'aud': 'other-client'},
                        {'nonce': 'wrong'}, {'azp': 'other-client'}, {'aud': ['asm3', 'other-client']}):
            with self.subTest(changes=changes), self.assertRaises(auth.AccessDenied):
                self.verify(self.token(changes))

    def test_rejects_missing_required_claims(self):
        for claim in ('iss', 'sub', 'aud', 'exp', 'iat', 'nonce'):
            with self.subTest(claim=claim), self.assertRaises(auth.AccessDenied):
                self.verify(self.token(remove=claim))

    def test_rejects_expired_future_and_invalid_subject_tokens(self):
        for changes in ({'exp': int(time.time()) - 30}, {'iat': int(time.time()) + 300},
                        {'nbf': int(time.time()) + 300}, {'sub': 42}, {'sub': ''},
                        {'sub': 'a' * 256}, {'exp': str(int(time.time()) + 300)}):
            with self.subTest(changes=changes), self.assertRaises(auth.AccessDenied):
                self.verify(self.token(changes))

    def test_rejects_remote_or_embedded_jwt_keys(self):
        for key in ('jku', 'jwk', 'x5u', 'crit'):
            with self.subTest(key=key), self.assertRaises(auth.AccessDenied):
                self.verify(self.token(headers={'kid': 'current', key: 'untrusted'}))

    def test_unsigned_or_symmetric_tokens_rejected(self):
        import jwt
        for algorithm, key in (('none', None), ('HS256', 'a' * 40)):
            with self.subTest(algorithm=algorithm), self.assertRaises(auth.AccessDenied):
                self.verify(jwt.encode(self.claims, key, algorithm=algorithm))

    def test_unknown_key_id_rejected(self):
        with self.assertRaises(auth.AccessDenied):
            self.verify(self.token(headers={'kid': 'unknown'}))

    def test_empty_policy_and_string_groups_do_not_grant_access(self):
        with self.assertRaises(auth.AccessDenied):
            self.verify(self.token({'groups': 'staff'}))
        self.cfg['allowed_groups'] = []
        with self.assertRaises(auth.AccessDenied):
            self.verify(self.token())
        self.cfg['allowed_subjects'] = ['stable-subject']
        self.assertTrue(self.verify(self.token()))

    def test_identity_namespace_includes_issuer(self):
        self.assertNotEqual(oidc.identity_key(self.cfg['issuer'], 'same-sub'),
                            oidc.identity_key('https://other.example.test', 'same-sub'))


class EndpointTests(unittest.TestCase):
    def test_insecure_or_credential_bearing_endpoints_rejected(self):
        for endpoint in ('http://localhost/token', 'https://user:password@example.test',
                         'https://example.test/#fragment', '//example.test/token', None):
            with self.subTest(endpoint=endpoint), self.assertRaises(auth.AccessDenied):
                oidc.https_url(endpoint)

    def test_state_rejected_without_a_browser_transaction(self):
        with self.assertRaises(auth.AccessDenied):
            oidc.callback({}, {}, '?code=stolen&state=not-a-session', None, '/src')

    def test_duplicate_state_rejected_before_token_exchange(self):
        tx = {'state': 'valid', 'expires': time.time()+60, 'fingerprint': 'cfg'}
        with patch.object(oidc, 'fingerprint', return_value='cfg'), patch.object(oidc, 'request_json') as http:
            with self.assertRaises(auth.AccessDenied):
                oidc.callback({'oidc_transaction': tx}, {}, '?state=valid&state=valid&code=x', None, '/src')
            http.assert_not_called()

class ConfigurationTests(unittest.TestCase):
    def load(self, data):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'oidc.json'
            path.write_text(json.dumps(data))
            return oidc.config(path)

    def test_disabled_oidc_needs_no_provider_or_credentials(self):
        self.assertEqual(self.load({'enabled': False}), {'enabled': False})

    def test_default_authorization_policy_denies_everyone(self):
        cfg = self.load({'enabled': True, 'issuer': 'https://id.example.test',
                         'client_id': 'asm3', 'client_secret': 'secret-sentinel'})
        self.assertFalse(oidc.allowed(cfg, {'sub': 'anyone', 'groups': ['admins']}))

    def test_bad_configuration_never_exposes_credentials(self):
        base = {'enabled': True, 'issuer': 'https://id.example.test',
                'client_id': 'asm3', 'client_secret': 'secret-sentinel'}
        for change in ({'session_max_age': 0}, {'allowed_groups': 'admins'},
                       {'issuer': 'http://id.example.test'}, {'enabled': 'true'},
                       {'ca_bundle': '../untrusted.pem'}, {'scopes': ['email']}):
            with self.subTest(change=change), self.assertRaises(auth.AccessDenied) as error:
                self.load(dict(base, **change))
            self.assertNotIn('secret-sentinel', str(error.exception))

    def test_discovery_cannot_change_issuer_or_downgrade_pkce(self):
        metadata = {'issuer': 'https://id.example.test', 'authorization_endpoint': 'https://id.example.test/auth',
                    'token_endpoint': 'https://id.example.test/token', 'jwks_uri': 'https://id.example.test/keys',
                    'response_types_supported': ['code'], 'id_token_signing_alg_values_supported': ['RS256']}
        cfg = {'issuer': metadata['issuer'], 'token_endpoint_auth_method': 'client_secret_basic'}
        for change in ({'issuer': 'https://attacker.test'}, {'token_endpoint': 'http://id.example.test/token'},
                       {'code_challenge_methods_supported': ['plain']}, {'id_token_signing_alg_values_supported': ['none']}):
            with self.subTest(change=change), patch.object(oidc, 'request_json', return_value=dict(metadata, **change)):
                with self.assertRaises(auth.AccessDenied):
                    oidc.discovery(cfg)

    def test_oidc_expiry_or_configuration_change_invalidates_session(self):
        cfg = {'enabled': True, 'allowed_subjects': ['subject'], 'allowed_groups': [], 'groups_claim': 'groups'}
        identity = {'fingerprint': 'current', 'deadline': time.time()+60, 'claims': {'sub': 'subject'}}
        with patch.object(oidc, 'fingerprint', return_value='current'):
            self.assertIs(oidc.checked_identity({'oidc_identity': identity}, cfg), identity)
            for change in ({'deadline': time.time()-1}, {'fingerprint': 'obsolete'}):
                with self.subTest(change=change), self.assertRaises(auth.AccessDenied):
                    oidc.checked_identity({'oidc_identity': dict(identity, **change)}, cfg)

    def test_expired_authorization_transaction_is_not_exchanged(self):
        transaction = {'state': 'valid', 'expires': time.time()-1}
        with patch.object(oidc, 'request_json') as http:
            with self.assertRaises(auth.AccessDenied):
                oidc.callback({'oidc_transaction': transaction}, {}, '?state=valid&code=x', None, '/src')
            http.assert_not_called()
