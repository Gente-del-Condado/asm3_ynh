#!/usr/bin/env python3
"""ONLY in a disposable YunoHost lab: real HTTPS OIDC, signed tokens, LDAP and ASM3.
Creates a local ephemeral provider and temporarily changes OIDC/staff settings.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import subprocess
import sys
import tomllib
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from oidc_fixture import Provider
from mfa_lab import complete


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disposable-lab', required=True, metavar='APP')
    p.add_argument('--lifecycle', action='store_true')
    p.add_argument('--algorithm', choices=('RS256', 'RS512'), default='RS256')
    args = p.parse_args()
    app = args.disposable_lab
    assert os.geteuid() == 0 and re.fullmatch(r'asm3(?:__\d+)?', app)
    import requests
    import urllib3
    urllib3.disable_warnings()

    def command(*parts):
        r = subprocess.run(parts, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError('Lab command failed: ' + ' '.join(parts[:4]))
        return r.stdout.strip()

    def setting(key):
        return command('yunohost', 'app', 'setting', app, key)

    root = Path(setting('install_dir'))
    os.environ['ASM3_CONF'] = str(root/'asm3.conf')
    sys.path.insert(0, str(root/'upstream/src'))
    import asm3.db
    import asm3.users
    import asm3.utils
    import ynh_oidc
    dbo = asm3.db.get_database()
    dbo.installpath = str(root/'upstream/src')+'/'
    base = 'https://' + setting('domain') + setting('path').rstrip('/')
    portal = 'https://' + setting('domain') + '/yunohost/portalapi/'
    admin = setting('admin')
    dummy = "Lab_"+secrets.token_urlsafe(32)
    command('yunohost', 'user', 'update', admin, '-p', dummy)
    config_path = root/'oidc.json'
    previous = config_path.read_bytes()
    gid = pwd.getpwnam(app).pw_gid
    provider = Provider()
    provider.algorithm = args.algorithm
    ca = root/'oidc-test-ca.pem'
    ca.write_bytes(provider.ca)
    os.chown(ca, 0, gid)
    os.chmod(ca, 0o640)
    cfg = {'enabled': True, 'issuer': provider.issuer, 'client_id': provider.client_id,
           'client_secret': provider.secret, 'ca_bundle': str(ca), 'id_token_signing_alg': args.algorithm,
           'token_endpoint_auth_method': 'client_secret_basic', 'scopes': ['openid','profile','email','groups'],
           'allowed_subjects': [], 'allowed_groups': ['asm3-staff'], 'groups_claim': 'groups',
           'ldap_links': {}, 'session_max_age': 300}
    results = []
    original_permissions = json.loads(command('yunohost', '--output-as', 'json', 'user', 'permission', 'info', app+'.staff'))['allowed']

    def check(label, ok):
        if not ok:
            raise AssertionError(label)
        results.append(label)
        print('PASS:', label, flush=True)

    def configure(data):
        config_path.write_text(json.dumps(data))
        os.chown(config_path, 0, gid)
        os.chmod(config_path, 0o640)

    def client():
        s = requests.Session()
        s.trust_env = False
        s.verify = False
        return s

    def get(s, route):
        return s.get(base+route, allow_redirects=False, timeout=20)

    def initiate(s):
        r = get(s, '/oidc/login')
        check('authorization redirect issued (HTTP '+str(r.status_code)+')', r.status_code == 303)
        q = parse_qs(urlsplit(r.headers['Location']).query)
        check('authorization code and PKCE S256 requested', q['response_type']==['code'] and q['code_challenge_method']==['S256'] and 'nonce' in q)
        r = s.get(r.headers['Location'], allow_redirects=False, verify=provider.ca_file, timeout=20)
        check('HTTPS provider issues code', r.status_code == 302)
        return r.headers['Location']

    def login(s=None):
        s = s or client()
        callback = initiate(s)
        r = s.get(callback, allow_redirects=False, timeout=20)
        if r.status_code==303 and r.headers.get("Location")==base+"/main":
            complete(s,base,dbo,check)
        return s, r, callback

    def app_config(s):
        complete(s,base,dbo,check)
        r = get(s, '/config.js')
        assert r.status_code == 200
        return json.loads(r.text[len('const asm = '):].rstrip(';'))

    try:
        # Apply with the shipped root helper; it validates discovery before writing.
        candidate = Path('/root/asm3-oidc-candidate.json')
        candidate.write_text(json.dumps(cfg))
        candidate.chmod(0o600)
        command(sys.executable, str(root/'ynh/manage_oidc.py'), '--app', app, '--config', str(candidate))
        candidate.unlink()
        check('OIDC configuration applied through validation helper', config_path.stat().st_mode & 0o777 == 0o640)
        s, r, callback = login()
        check('OIDC callback reaches private main', r.status_code == 303 and r.headers.get('Location') == base+'/main')
        check('OIDC private page available without portal', get(s, '/main').status_code == 200)
        user = app_config(s)
        check('automatic profile is separate and read only', user['user'].startswith('oidc_') and user['superuser']==0 and user['securitymap']=='va *')
        username = user['user']
        for method in ('client_secret_post', 'none'):
            configure(dict(cfg, token_endpoint_auth_method=method))
            alternate, response, _ = login()
            check(method+' completes PKCE login with the same profile', response.status_code==303 and app_config(alternate)['user']==username)
        configure(cfg)
        provider.subject='email-collision-subject'
        original_email, original_name = provider.email, provider.name
        provider.email=dbo.query_string('SELECT EmailAddress FROM users WHERE ID=1')
        provider.name=admin
        other, response, _ = login()
        check('matching administrator name and email never links accounts', response.status_code==303 and app_config(other)['user']!=admin and app_config(other)['superuser']==0)
        provider.subject='external-subject'
        provider.email, provider.name = original_email, original_name
        provider.scenario='short_lived'
        expiring, response, _ = login()
        check('short lived ID token starts a bounded session', response.status_code==303)
        time.sleep(7)
        check('ID token expiry closes OIDC session without refresh', get(expiring,'/main').status_code==403)
        provider.scenario=''
        userid = dbo.query_int('SELECT ID FROM users WHERE UserName=?', [username])
        check('profile stores verified name and email', user['userreal']==provider.name and user['useremail']==provider.email)
        check('backend exchanged code with matching PKCE and redirect URI', provider.exchanges[-1]['pkce'] and provider.exchanges[-1]['redirect_uri']==base+'/oidc/callback')
        check('browser cookies contain no OAuth tokens', all('ACCESS_TOKEN' not in c.value and 'REFRESH_TOKEN' not in c.value and provider.tokens[-1] not in c.value for c in s.cookies))
        check('replayed callback is rejected', s.get(callback, allow_redirects=False, timeout=20).status_code == 403)
        s, r, _ = login()
        check('same issuer and subject reuse the same profile', app_config(s)['user']==username)
        check('one profile mapping per identity', dbo.query_int('SELECT COUNT(*) FROM ynh_oidc_identity WHERE Issuer=? AND Subject=?', [provider.issuer,provider.subject])==1)
        role = dbo.insert('role', {'RoleName':'OIDC test role','SecurityMap':'vp *'}, setCreated=False)
        dbo.insert('userrole', {'UserID':userid,'RoleID':role}, generateID=False)
        check('role updates take effect without new login', 'vp ' in app_config(s)['securitymap'])
        dbo.execute('UPDATE users SET DisableLogin=1 WHERE ID=?', [userid])
        check('disabled profile immediately rejected', get(s,'/main').status_code==403)
        dbo.execute('UPDATE users SET DisableLogin=0 WHERE ID=?', [userid])
        s, r, _ = login()
        configure(dict(cfg, allowed_groups=[]))
        check('policy removal invalidates existing OIDC session', get(s,'/main').status_code==403)
        _, denied, _ = login()
        check('empty allowlist denies new OIDC login', denied.status_code==403)
        configure(cfg)
        for scenario in ('bad_nonce','bad_audience','bad_issuer','expired','unsigned','token_error'):
            provider.scenario = scenario
            _, denied, _ = login()
            check(scenario+' is rejected without exposing provider data', denied.status_code==403 and 'SENSITIVE_PROVIDER_ERROR' not in denied.text)
        provider.scenario = ''
        bad = client()
        callback = initiate(bad)
        parsed = urlsplit(callback)
        q = parse_qs(parsed.query)
        q['state'] = ['forged-state']
        forged = parsed._replace(query=urlencode(q,doseq=True)).geturl()
        exchanges_before = len(provider.exchanges)
        check('forged state rejected before token exchange', bad.get(forged,allow_redirects=False,timeout=20).status_code==403 and len(provider.exchanges)==exchanges_before)
        victim = client()
        callback = initiate(victim)
        check('code from a different browser is rejected', client().get(callback,allow_redirects=False,timeout=20).status_code==403)
        s, r, _ = login()
        # Local passwords cannot substitute for the OIDC flow.
        secret = secrets.token_urlsafe(30)
        dbo.execute('UPDATE users SET Password=? WHERE ID=?', [asm3.users.hash_password(secret),userid])
        local = client()
        get(local,'/login?local=1')
        r = local.post(base+'/login?local=1',data={'username':username,'password':secret},timeout=20)
        check('OIDC profile local password bypass blocked', r.text=='FAIL')
        r = client().post(base+'/service',data={'method':'json_report','username':username,'password':secret},timeout=20)
        check('OIDC profile cannot bypass login through password API', 'Password API is disabled by mandatory MFA policy' in r.text)
        # Existing factors are reused by the mandatory package challenge.
        otp = asm3.utils.otp_secret()
        dbo.execute('UPDATE users SET EnableTOTP=1, OTPSecret=? WHERE ID=?', [otp,userid])
        s,r,_ = login()
        check('OIDC reuses an existing factor through mandatory MFA', get(s,'/main').status_code==200)
        # Native portal authentication and OIDC can be selected independently.
        a=client()
        check('native portal remains available', a.post(portal+'login',data={'credentials':admin+':'+dummy},timeout=20).status_code==200)
        check('native SSO entry remains available', get(a,'/ynh_sso').status_code==303 and app_config(a)['user']==admin)
        a,r,_=login(a)
        check('explicit OIDC entry switches away from native identity', r.status_code==303 and app_config(a)['user']==username)
        check('explicit native entry restores LDAP identity', get(a,'/ynh_sso').status_code==303 and app_config(a)['user']==admin)
        # Only an explicit root-controlled link may grant the existing LDAP roles.
        provider.subject='linked-ldap-subject'
        linked_cfg=dict(cfg,ldap_links={provider.subject:admin})
        configure(linked_cfg)
        a,r,_=login()
        check('explicit LDAP link reuses selected profile', r.status_code==303 and app_config(a)['user']==admin)
        command('yunohost','user','permission','add',app+'.staff',admin)
        for grant in original_permissions:
            if grant != admin:
                command('yunohost','user','permission','remove',app+'.staff',grant)
        command('yunohost','user','permission','remove',app+'.staff',admin)
        check('LDAP revocation also invalidates linked OIDC session', get(a,'/main').status_code==403)
        command('yunohost','user','permission','add',app+'.staff',admin,*original_permissions)
        configure(cfg)
        provider.subject='external-subject'
        s,r,_=login()
        # RP-initiated logout uses only client ID and a fixed registered callback.
        r=get(s,'/oidc/logout')
        check('OIDC logout redirects to discovered provider', r.status_code==303 and r.headers['Location'].startswith(provider.issuer+'/logout?'))
        check('logout URL contains no ID token', 'id_token_hint' not in r.headers['Location'])
        r=s.get(r.headers['Location'],allow_redirects=False,verify=provider.ca_file,timeout=20)
        r=s.get(r.headers['Location'],allow_redirects=False,timeout=20)
        check('OIDC logout callback validates state', r.status_code==303 and r.headers['Location']==base+'/login?loggedout=1')
        check('logout leaves private session closed', get(s,'/main').status_code!=200)
        check('forged logout callback rejected', get(client(),'/oidc/logged_out?state=forged').status_code==403)
        recovery=client()
        get(recovery,'/login?local=1')
        r=recovery.post(base+'/login?local=1',data={'username':'ynh_rescue_'+app,'password':setting('rescue_password')},timeout=20)
        check('local recovery remains available alongside OIDC', r.text=='ynh_rescue_'+app)
        if args.lifecycle:
            backup='asm3-oidc-'+secrets.token_hex(4)
            command('yunohost','backup','create','--name',backup,'--apps',app)
            command('yunohost','app','remove',app)
            command('yunohost','backup','restore',backup,'--apps',app,'--force')
            check('OIDC configuration and CA survive restore', json.loads(config_path.read_text())==cfg and ca.read_bytes()==provider.ca)
            s,r,_=login()
            check('restored OIDC profile and assigned roles work', r.status_code==303 and app_config(s)['user']==username and 'vp ' in app_config(s)['securitymap'])
        journal=command('journalctl','-u',app,'--no-pager')
        secrets_to_check=[provider.secret,secret,*provider.tokens,'ACCESS_TOKEN_MUST_NOT_LEAK','REFRESH_TOKEN_MUST_NOT_LEAK','SENSITIVE_PROVIDER_ERROR']
        check('tokens and credentials absent from journal', all(value not in journal for value in secrets_to_check))
        access=Path('/var/log/nginx/'+setting('domain')+'-access.log')
        check('tokens absent from Nginx access log', not access.exists() or all(t not in access.read_text() for t in provider.tokens))
        report={'package_version':tomllib.loads(Path('/etc/yunohost/apps/'+app+'/manifest.toml').read_text())['version'],'provider':'ephemeral HTTPS provider with genuine '+args.algorithm+' tokens and PKCE enforcement','algorithm':args.algorithm,'checks':results,'result':'success'}
        Path('/root/asm3-oidc-results.json').write_text(json.dumps(report,indent=2)+'\n')
    finally:
        config_path.write_bytes(previous)
        os.chown(config_path,0,gid)
        os.chmod(config_path,0o640)
        subprocess.run(['systemctl','restart',app],capture_output=True)
        subprocess.run(['yunohost','user','permission','add',app+'.staff',*original_permissions],capture_output=True)
        provider.close()
        ca.unlink(missing_ok=True)
        # Release only this ephemeral provider's links; never retain an admin link
        # that could make a later independent fixture collide with the same user.
        try:
            dbo.execute('DELETE FROM ynh_oidc_identity WHERE Issuer=?', [provider.issuer])
        except Exception:
            pass


if __name__=='__main__':
    main()
