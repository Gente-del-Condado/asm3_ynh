#!/usr/bin/env python3
"""Destructive integration checks, ONLY inside a disposable YunoHost container.
Usage: python3 tools/test_yunohost_sso.py --disposable-lab asm3
Creates a temporary directory user and changes permissions during the test.
Never run against a production installation.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-lab', required=True, metavar='APP')
    parser.add_argument('--lifecycle', action='store_true', help='Also remove and restore the app from a real backup')
    args = parser.parse_args()
    app = args.disposable_lab
    assert re.fullmatch(r'asm3(?:__\d+)?', app)
    import requests
    import urllib3
    urllib3.disable_warnings()

    def command(*parts):
        result = subprocess.run(parts, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError('Lab command failed: ' + ' '.join(parts[:4]))
        return result.stdout.strip()

    def setting(key):
        return command('yunohost', 'app', 'setting', app, key)

    root = Path(setting('install_dir'))
    os.environ['ASM3_CONF'] = str(root / 'asm3.conf')
    sys.path.insert(0, str(root / 'upstream/src'))
    import asm3.db
    import asm3.users
    import asm3.utils
    import ynh_auth
    dbo = asm3.db.get_database()
    dbo.installpath = str(root / 'upstream/src') + '/'
    admin = setting('admin')
    base = 'https://' + setting('domain') + setting('path').rstrip('/')
    portal = 'https://' + setting('domain') + '/yunohost/portalapi/'
    # The dummy password is reset only in this disposable container.
    dummy = secrets.token_urlsafe(30)
    command('yunohost', 'user', 'update', admin, '-p', dummy)
    uid = 'asm3_sso_probe'
    subprocess.run(['yunohost', 'user', 'delete', uid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dbo.execute('DELETE FROM userrole WHERE UserID IN (SELECT ID FROM users WHERE UserName=?)', [uid])
    dbo.execute('DELETE FROM ynh_auth_identity WHERE UserID IN (SELECT ID FROM users WHERE UserName=?)', [uid])
    dbo.execute('DELETE FROM users WHERE UserName=?', [uid])
    command('yunohost', 'user', 'create', uid, '--domain', setting('domain'), '--fullname', 'SSO Probe', '--password', dummy)
    passed = []

    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        passed.append(label)
        print('PASS:', label, flush=True)

    def client():
        s = requests.Session()
        s.trust_env = False
        s.verify = False
        return s

    def get(s, path, **kwargs):
        return s.get(base + path, allow_redirects=False, timeout=20, **kwargs)

    def login(user):
        s = client()
        r = s.post(portal + 'login', data={'credentials': user + ':' + dummy}, timeout=20)
        check('portal login ' + user, r.status_code == 200)
        return s

    def enter(s):
        r = get(s, '/ynh_sso')
        check('SSO redirects to private main', r.status_code == 303 and r.headers.get('Location') == base + '/main')
        check('private main is available', get(s, '/main').status_code == 200)

    try:
        anon = client()
        check('local recovery form available', get(anon, '/login?local=1').status_code == 200)
        spoof = client()
        r = get(spoof, '/main', headers={'YNH_USER': admin, 'X-ASM3-Proxy-Secret': 'forged'})
        check('SSOwat rejects forged identity headers', r.status_code != 200)
        r = requests.get('http://127.0.0.1:' + setting('port') + '/main', headers={'YNH_USER': admin}, timeout=10)
        check('direct loopback bypass rejected', r.status_code == 403)
        check('Nginx proxy secret is root only', Path('/etc/nginx/conf.d/' + setting('domain') + '.d/' + app + '.conf').stat().st_mode & 0o777 == 0o600)
        # Configure public access independently of the private staff grant.
        command('yunohost', 'user', 'permission', 'add', app + '.main', 'visitors')
        command('yunohost', 'user', 'permission', 'add', app + '.staff', admin, uid)
        command('yunohost', 'user', 'permission', 'remove', app + '.staff', 'all_users')
        r = get(client(), '/service?method=invalid')
        check('public service remains reachable without portal', r.status_code == 500 and "Invalid method 'invalid'" in r.text)
        a = login(admin)
        enter(a)
        check('selected administrator explicitly linked', ynh_auth.identity_row(dbo, ynh_auth.directory_user(admin)['subject'])[0].USERID == 1)
        b = login(uid)
        enter(b)
        person = ynh_auth.directory_user(uid)
        user = ynh_auth.provision(dbo, person)
        check('automatic profile has no superuser access', user.SUPERUSER == 0)
        check('automatic profile has read only role', asm3.users.get_security_map(dbo, user.ID) == 'va *')
        for _ in range(3):
            get(b, '/main')
        check('provisioning is idempotent', dbo.query_int('SELECT COUNT(*) FROM ynh_auth_identity WHERE Subject=?', [person['subject']]) == 1)
        original_role = dbo.query_int('SELECT RoleID FROM userrole WHERE UserID=?', [user.ID])
        extra_role = dbo.insert('role', {'RoleName': 'SSO integration test', 'SecurityMap': 'vp *'}, setCreated=False)
        dbo.insert('userrole', {'UserID': user.ID, 'RoleID': extra_role}, generateID=False)
        get(b, '/main')
        check('assigned roles survive profile sync', set(asm3.users.get_roles_ids_for_userid(dbo, user.ID)) == {original_role, extra_role})
        original_name, original_email = person['name'], person['email']
        dbo.execute('UPDATE users SET RealName=?, EmailAddress=? WHERE ID=?', ['outdated profile', 'outdated@example.test', user.ID])
        get(b, '/main')
        updated = dbo.query('SELECT RealName, EmailAddress FROM users WHERE ID=?', [user.ID])[0]
        check('name and email synchronized from LDAP', updated.REALNAME == original_name and updated.EMAILADDRESS == original_email)
        # A portal identity switch must discard the prior administrator's roles.
        a.get(portal + 'logout', timeout=20)
        r = a.post(portal + 'login', data={'credentials': uid + ':' + dummy}, timeout=20)
        check('portal identity switch login works', r.status_code == 200)
        get(a, '/main')
        cfg = get(a, '/config.js')
        config = json.loads(cfg.text[len('const asm = '):].rstrip(';'))
        check('identity switch drops administrator privileges', config['user'] == uid and config['superuser'] == 0)

        dbo.execute('UPDATE users SET DisableLogin=1 WHERE ID=?', [user.ID])
        check('disabled profile rejected on next request', get(b, '/main').status_code == 403)
        dbo.execute('UPDATE users SET DisableLogin=0 WHERE ID=?', [user.ID])
        enter(b)
        command('yunohost', 'user', 'permission', 'remove', app + '.staff', uid)
        check('LDAP revocation invalidates existing session', get(b, '/main').status_code == 403)
        command('yunohost', 'user', 'permission', 'add', app + '.staff', uid)
        enter(b)
        before = b.cookies.get('asm_session_id_' + app)
        r = get(b, '/logout')
        check('local logout returns to login', r.status_code == 303)
        check('local logout rotates session cookie', b.cookies.get('asm_session_id_' + app) != before)
        check('local logout does not silently sign in again', get(b, '/login?loggedout=1').status_code == 200)
        enter(b)
        b.get(portal + 'logout', timeout=20)
        check('portal logout invalidates private ASM session', get(b, '/main').status_code != 200)
        # A managed account cannot authenticate with its old/local password.
        secret = secrets.token_urlsafe(32)
        dbo.execute('UPDATE users SET Password=? WHERE ID=?', [asm3.users.hash_password(secret), user.ID])
        r = anon.post(base + '/login?local=1', data={'username': uid, 'password': secret}, timeout=20)
        check('managed local password bypass blocked', r.text == 'FAIL')
        # Native TOTP is preserved rather than bypassed by SSO.
        otpsecret = asm3.utils.otp_secret()
        dbo.execute('UPDATE users SET EnableTOTP=1, OTPSecret=? WHERE ID=?', [otpsecret, user.ID])
        b = login(uid)
        r = get(b, '/ynh_sso')
        check('2FA identity requires challenge', r.status_code == 303 and r.headers['Location'] == base + '/login')
        r = get(b, '/login')
        match = re.search(r'controller = (.*);', r.text)
        controller = json.loads(match.group(1))
        token = controller['hpassword']
        data = {'username': controller['husername'], 'password': token}
        check('2FA nonce alone does not authenticate', b.post(base + '/login', data=data, timeout=20).text == 'ASK2FA')
        data['onetimepass'] = 'wrong'
        check('incorrect TOTP rejected', b.post(base + '/login', data=data, timeout=20).text == 'BAD2FA')
        data['onetimepass'] = str(asm3.utils.totp(otpsecret))
        check('correct TOTP completes SSO', b.post(base + '/login', data=data, timeout=20).text == uid)
        check('2FA private page available', get(b, '/main').status_code == 200)
        dbo.execute('UPDATE users SET EnableTOTP=0 WHERE ID=?', [user.ID])
        # Same username with a different directory identifier may never claim data.
        altered = dict(person, subject='00000000-0000-0000-0000-000000000000')
        try:
            ynh_auth.provision(dbo, altered)
            collision_denied = False
        except ynh_auth.AccessDenied:
            collision_denied = True
        check('recreated identity cannot claim old profile', collision_denied)
        # Recover without LDAP or a portal session.
        rescue = 'ynh_rescue_' + app
        c = client()
        get(c, '/login?local=1')
        r = c.post(base + '/login?local=1', data={'username': rescue, 'password': setting('rescue_password')}, timeout=20)
        check('local recovery account works', r.text == rescue and get(c, '/main').status_code == 200)
        # Log redaction: desktop, mobile, malformed base64, service authentication.
        marker = 'ASM3_PASSWORD_MUST_NEVER_BE_LOGGED_' + secrets.token_hex(8)
        c = client()
        for endpoint in ('/login?local=1', '/mobile_login?local=1'):
            c.post(base + endpoint, data={'username': 'bad_user', 'password': marker}, timeout=20)
            c.get(base + endpoint + '&b=' + marker, timeout=20)
        r = c.post(base + '/service', data={'method': 'json_report', 'username': 'bad_user', 'password': marker}, timeout=20)
        check('API failed authentication path exercised', 'Invalid username and password' in r.text)
        c.get(base + '/service', params={'method': 'invalid', 'password': marker}, timeout=20)
        journal = command('journalctl', '-u', app, '--no-pager')
        check('passwords and malformed credentials absent from journal', marker not in journal and secret not in journal and token not in journal)
        access = Path('/var/log/nginx/' + setting('domain') + '-access.log')
        check('credentials absent from Nginx access log', not access.exists() or marker not in access.read_text())
        logs = Path('/var/log/yunohost/categories/operation')
        for secret_name in ('proxy_secret', 'rescue_password'):
            value = setting(secret_name)
            check(secret_name + ' absent from operation logs', all(value not in f.read_text(errors='replace') for f in logs.glob('*' + app + '*.log')))
        if args.lifecycle:
            subject = person['subject']
            backup = 'asm3-sso-' + secrets.token_hex(4)
            mapping_before = dbo.query_int('SELECT UserID FROM ynh_auth_identity WHERE Subject=?', [subject])
            command('yunohost', 'backup', 'create', '--name', backup, '--apps', app)
            command('yunohost', 'app', 'remove', app)
            command('yunohost', 'backup', 'restore', backup, '--apps', app, '--force')
            # New connection in a fresh interpreter after recreation of the DB user.
            code = 'import asm3.db; print(asm3.db.get_database().query_int("SELECT UserID FROM ynh_auth_identity WHERE Subject=?", [' + repr(subject) + ']))'
            environment = dict(os.environ, PYTHONPATH=str(root / 'upstream/src'))
            result = subprocess.run([sys.executable, '-c', code], env=environment, capture_output=True, text=True, check=True)
            check('LDAP identity mapping survives remove and restore', int(result.stdout.strip()) == mapping_before)
            restored = login(admin)
            enter(restored)
            restored = login(uid)
            enter(restored)
            cfg = get(restored, '/config.js')
            config = json.loads(cfg.text[len('const asm = '):].rstrip(';'))
            check('roles and non-admin profile survive restore', config['user'] == uid and config['superuser'] == 0 and 'vp ' in config['securitymap'])
        report = {'package_version': '51.1~ynh3', 'checks': passed, 'result': 'success'}
        Path('/root/asm3-sso-results.json').write_text(json.dumps(report, indent=2) + '\n')
    finally:
        # Keep only the fictitious SQL profile as evidence; remove its directory grant.
        subprocess.run(['yunohost', 'user', 'delete', uid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        command('yunohost', 'user', 'permission', 'add', app + '.staff', 'all_users')


if __name__ == '__main__':
    main()
