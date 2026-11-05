"""Security boundary regressions; real LDAP/SSOwat checks live in the lab suite."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


auth = module('ynh_auth_test', 'conf/ynh_auth.py')
server = module('ynh_server_test', 'conf/server.py')


class ProxyTrustTests(unittest.TestCase):
    def test_forged_and_missing_secret_cannot_reach_application(self):
        for supplied in ('', 'wrong', 'trusted-extra'):
            app = MagicMock()
            respond = MagicMock()
            result = server.ProxyApplication(app, '/refugio', secret='trusted')({
                'PATH_INFO': '/main', 'HTTP_YNH_USER': 'admin',
                'HTTP_X_ASM3_PROXY_SECRET': supplied}, respond)
            self.assertEqual(result, [b'Trusted proxy required'])
            self.assertEqual(respond.call_args.args[0], '403 Forbidden')
            app.assert_not_called()

    def test_trusted_proxy_can_supply_identity(self):
        got = {}
        def app(env, respond):
            got.update(env)
            return [b'ok']
        proxy = server.ProxyApplication(app, '/', secret='trusted')
        proxy({'PATH_INFO': '/main', 'REMOTE_ADDR': '127.0.0.1',
               'HTTP_X_ASM3_PROXY_SECRET': 'trusted', 'HTTP_YNH_USER': 'alice'}, MagicMock())
        self.assertEqual(got['asm3.ynh_user'], 'alice')

    def test_public_health_exposes_no_identity_or_application(self):
        app = MagicMock()
        response = server.ProxyApplication(app, '/', secret='trusted')({'PATH_INFO': '/_ynh_health'}, MagicMock())
        self.assertEqual(response, [b'ready'])
        app.assert_not_called()


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.response = [{'type': 'searchResEntry', 'attributes': {
            'uid': ['alice'], 'entryUUID': ['stable-id'], 'displayName': ['Alice'], 'mail': ['alice@example.test']}}]
        self.connection = MagicMock()
        self.connection.return_value.__enter__.return_value = self.conn
        ldap = types.ModuleType('ldap3')
        ldap.Connection = self.connection
        ldap.Server = MagicMock()
        ldap.NONE = 'none'
        ldap.SUBTREE = 'subtree'
        conv = types.ModuleType('ldap3.utils.conv')
        conv.escape_filter_chars = lambda x: x
        site = types.ModuleType('asm3.sitedefs')
        site.get_string = lambda key: 'asm3__2'
        self.modules = patch.dict(sys.modules, {'ldap3': ldap, 'ldap3.utils.conv': conv,
                                                'asm3': types.ModuleType('asm3'), 'asm3.sitedefs': site})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_staff_permission_and_stable_uuid_are_required(self):
        person = auth.directory_user('alice')
        self.assertEqual(person['subject'], 'stable-id')
        query = self.conn.search.call_args.args[1]
        self.assertIn('(permission=cn=asm3__2.staff,ou=permission,dc=yunohost,dc=org)', query)
        self.assertFalse(self.connection.call_args.kwargs['auto_referrals'])
        self.assertTrue(self.connection.call_args.kwargs['read_only'])

    def test_empty_or_ambiguous_directory_result_is_denied(self):
        row = self.conn.response[0]
        for rows in ([], [row, row]):
            self.conn.response = rows
            with self.assertRaises(auth.AccessDenied):
                auth.directory_user('alice')

    def test_filter_injection_never_reaches_directory(self):
        with self.assertRaises(auth.AccessDenied):
            auth.directory_user('alice)(uid=*)')
        self.connection.assert_not_called()

    def test_directory_failure_does_not_expose_exception_secrets(self):
        self.connection.side_effect = RuntimeError('SECRET_SENTINEL')
        with self.assertRaises(auth.AccessDenied) as error:
            auth.directory_user('alice')
        self.assertNotIn('SECRET_SENTINEL', str(error.exception))

    def test_missing_stable_identifier_is_denied(self):
        del self.conn.response[0]['attributes']['entryUUID']
        with self.assertRaises(auth.AccessDenied):
            auth.directory_user('alice')

class PublicBoundaryTests(unittest.TestCase):
    def test_embedded_animals_do_not_retain_revoked_sso_identity(self):
        # ASM3 labels this route check_logged_in=False, but it can use the
        # current session's animal permissions. It must cross the SSO gate.
        session = {'user': 'alice', 'ynh_source': 'sso'}
        web = types.ModuleType('web070')
        web.ctx = types.SimpleNamespace(path='/animal_embed', method='GET', env={})
        web.input = lambda: {}
        package = types.ModuleType('asm3')
        package.db = types.ModuleType('asm3.db')
        package.users = types.ModuleType('asm3.users')
        site = types.ModuleType('asm3.sitedefs')
        site.BASE_URL = 'https://example.test/refugio'
        with patch.dict(sys.modules, {'web070': web, 'asm3': package,
                                     'asm3.db': package.db, 'asm3.users': package.users,
                                     'asm3.sitedefs': site}), patch.object(auth, 'reset_session', side_effect=lambda s: s.clear()):
            handler = MagicMock(side_effect=lambda: session.get('user'))
            self.assertIsNone(auth.processor(session, '/src/')(handler))
            handler.assert_called_once()


if __name__ == '__main__':
    unittest.main()
