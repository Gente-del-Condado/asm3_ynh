"""Mandatory MFA and managed Dex policy regressions."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value
mfa=module('mfa_test','conf/ynh_mfa.py')
manager=module('identity_test','conf/manage_identity.py')

class MFATests(unittest.TestCase):
    def test_rfc6238_sha1_vectors(self):
        seed='GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
        for timestamp,expected in ((59,'287082'),(1111111109,'081804'),(1111111111,'050471'),(1234567890,'005924'),(2000000000,'279037'),(20000000000,'353130')):
            self.assertEqual(mfa.totp(seed,timestamp//30),expected)
    def test_strict_format_window_and_replay(self):
        seed='GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
        code=mfa.totp(seed,100)
        self.assertEqual(mfa.verify_code(seed,code,-1,3000),100)
        self.assertIsNone(mfa.verify_code(seed,code,100,3000))
        self.assertIsNone(mfa.verify_code(seed,code,-1,3090))
        for bad in ('１２３４５６','12345','1234567',' 123456','abcdef'):
            self.assertIsNone(mfa.verify_code(seed,bad,-1,3000))
    def test_page_semantics_and_no_secret_in_url(self):
        class Session(dict):
            __getattr__=dict.__getitem__
        session=Session(mfa_pending={'csrf':'token','enroll_seed':'SEED'})
        class User(dict):USERNAME='alice'
        with patch.object(mfa,'headers'):
            page=mfa.page(session,User(),'/asm3')
        for expected in ('<main>','<label for="code">','method="post"','autocomplete="one-time-code"','inputmode="numeric"','/auth/mfa/qr'):
            self.assertIn(expected,page)
        self.assertNotIn('?secret=',page)
        self.assertNotIn('type="number"',page)

class LogTests(unittest.TestCase):
    def test_configuration_helper_output_is_redacted_and_failure_preserved(self):
        import subprocess
        script='source "$1"; fake_output() { printf "%s\\n" "proxy_set_header X-ASM3-Proxy-Secret SENTINEL" "plain diagnostic" "smtp_password=OTHER_SENTINEL"; return 7; }; asm3_safe_config fake_output'
        result=subprocess.run(['bash','-c',script,'lab',str(ROOT/'scripts/_common.sh')],capture_output=True,text=True)
        self.assertEqual(result.returncode,7)
        self.assertNotIn('SENTINEL',result.stdout+result.stderr)
        self.assertIn('plain diagnostic',result.stdout)
        self.assertIn('[redacted configuration line]',result.stdout)

class DexTests(unittest.TestCase):
    def test_blank_secrets_preserve_stored_value(self):
        previous=dict(manager.DEFAULTS,google_client_secret='protected')
        self.assertEqual(manager.candidate(previous,{'google_client_secret':''})['google_client_secret'],'protected')
    def test_enabled_cloud_provider_requires_credentials(self):
        for provider in ('google','github','microsoft'):
            with self.assertRaises(manager.ConfigError):manager.candidate(manager.DEFAULTS,{provider+'_login':'true'})
    def test_microsoft_requires_specific_tenant(self):
        with self.assertRaises(manager.ConfigError):manager.candidate(manager.DEFAULTS,{'microsoft_login':'true','microsoft_client_id':'id','microsoft_client_secret':'secret','microsoft_tenant':'common'})
    def test_preserves_other_apps_and_owns_only_its_connectors(self):
        head={'issuer':'https://dex.example.test','connectors':[{'id':'ldap','type':'ldap'},{'id':'other-google','type':'google'},{'id':'asm3-asm3-google','type':'google'}]}
        data=dict(manager.DEFAULTS,google_login=True,google_client_id='id',google_client_secret='secret')
        output,env,allowed=manager.render_connectors('asm3',data,head)
        self.assertEqual([c['id'] for c in output['connectors']],['ldap','other-google','asm3-asm3-google'])
        self.assertEqual(allowed,['ldap','asm3-asm3-google'])
        self.assertEqual(env['ASM3_ASM3_GOOGLE_CLIENT_SECRET'],'secret')
        self.assertNotIn('secret',str(output))
    def test_generator_keeps_static_clients_as_last_open_list(self):
        import yaml
        output=manager.dump_head({"issuer":"https://dex.example.test","staticClients":None,"connectors":[]})
        generated=output+b"\n- id: asm3\n  secretEnv: SECRET\n"
        self.assertEqual(yaml.safe_load(generated)["staticClients"][0]["id"],"asm3")

    def test_microsoft_keeps_required_graph_default_scope(self):
        head={'issuer':'https://dex.example.test','connectors':[{'id':'ldap','type':'ldap'}]}
        data=dict(manager.DEFAULTS,microsoft_login=True,microsoft_client_id='id',microsoft_client_secret='secret',microsoft_tenant='11111111-1111-1111-1111-111111111111')
        output,_,_=manager.render_connectors('asm3',data,head)
        microsoft=output['connectors'][-1]['config']
        self.assertNotIn('scopes',microsoft) # Dex injects user.read; OIDC-only overrides break Graph /me.
        self.assertEqual(microsoft['tenant'],data['microsoft_tenant'])

    def test_environment_escaping_does_not_use_shell(self):
        self.assertEqual(manager.env_file({'KEY':'x$(`z`)"\\y'}),b'KEY="x$(`z`)\\"\\\\y"\n')
