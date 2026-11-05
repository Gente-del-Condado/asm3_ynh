#!/usr/bin/env python3
"""Destructive lab only: actual Dex LDAP federation, panel, mandatory MFA, social config."""
import argparse
import html
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from urllib.parse import urljoin,urlsplit,parse_qs
import yaml


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-lab',required=True)
    parser.add_argument('--lifecycle',action='store_true')
    args=parser.parse_args();app=args.disposable_lab
    assert os.geteuid()==0 and re.fullmatch(r'asm3(?:__\d+)?',app)
    def command(*parts):
        r=subprocess.run(parts,capture_output=True,text=True)
        if r.returncode:raise RuntimeError('Lab operation failed: '+' '.join(parts[:4]))
        return r.stdout.strip()
    def setting(key):return command('yunohost','app','setting',app,key)
    root=Path(setting('install_dir'));os.environ['ASM3_CONF']=str(root/'asm3.conf')
    sys.path.insert(0,str(root/'upstream/src'))
    import asm3.db,ynh_auth,ynh_mfa
    import requests,urllib3
    urllib3.disable_warnings()
    dbo=asm3.db.get_database();dbo.installpath=str(root/'upstream/src')+'/'
    base='https://'+setting('domain')+setting('path').rstrip('/')
    admin=setting('admin');password="Lab_"+secrets.token_urlsafe(32)
    command('yunohost','user','update',admin,'-p',password)
    prior_operation_logs=set(Path('/var/log/yunohost/operations').glob('*.log'))
    checks=[]
    def check(label,ok):
        assert ok,label
        checks.append(label);print('PASS:',label,flush=True)
    def client():
        s=requests.Session();s.trust_env=False;s.verify=False;return s
    def get(s,path):return s.get(base+path,allow_redirects=False,timeout=20)
    def panel(data):
        path=Path('/root/asm3-dex-panel.json');path.write_text(json.dumps(data));path.chmod(0o600)
        try:return command('yunohost','app','config','set',app,'identity.access','--args-file',str(path))
        finally:path.unlink(missing_ok=True)
    def fields(text):
        return {name:value for name,value in re.findall(r'name="([^"]+)"[^>]*value="([^"]*)"',text)}
    def otp_page(s):
        r=get(s,'/main')
        check('first factor cannot access private data',r.status_code==303 and r.headers['Location']==base+'/auth/mfa')
        r=get(s,'/auth/mfa');check('mandatory challenge rendered',r.status_code==200 and 'segundo factor' in r.text)
        return r
    dexroot=Path(command('yunohost','app','setting','dex','install_dir'))
    foreign=dexroot/'config.yaml.d/asm3-other-fixture.yaml'
    foreign.write_text('- id: asm3-other-fixture\n  name: Other fixture app\n  public: true\n  redirectURIs: [https://example.test/callback]\n')
    foreign.chmod(0o644)
    foreign_bytes=foreign.read_bytes()
    cfg={'dex_enabled':True,'dex_ldap_login':True,'allowed_groups':'all_users',
         'google_login':False,'github_login':False,'microsoft_login':False,
         'dex_ca_file':'/etc/yunohost/certs/'+setting('domain')+'/crt.pem'}
    original_main=json.loads(command('yunohost','--output-as','json','user','permission','info',app+'.main'))['allowed']
    if 'visitors' in original_main:
        command('yunohost','user','permission','remove',app+'.main','visitors')
    panel(cfg)
    check('managed entry grants visitors through nested YunoHost API','visitors' in json.loads(command('yunohost','--output-as','json','user','permission','info',app+'.main'))['allowed'])
    panel({'allow_external_entry':False})
    check('external entry toggle revokes only its owned visitor grant','visitors' not in json.loads(command('yunohost','--output-as','json','user','permission','info',app+'.main'))['allowed'])
    panel({'allow_external_entry':True})
    check('external entry can be re-enabled','visitors' in json.loads(command('yunohost','--output-as','json','user','permission','info',app+'.main'))['allowed'])
    check('YunoHost panel enables shared Dex',json.loads((root/'oidc.json').read_text())['managed_by']=='asm3-dex')
    # Root-only reset deliberately forces a new enrollment for this disposable LDAP identity.
    ynh_auth.provision(dbo,ynh_auth.directory_user(admin))
    ynh_mfa.reset_user(dbo,admin)
    issuer=json.loads((root/'oidc.json').read_text())['issuer']
    for user in dbo.query('SELECT u.UserName FROM users u JOIN ynh_oidc_identity i ON i.UserID=u.ID WHERE i.Issuer=?',[issuer]):
        ynh_mfa.reset_user(dbo,user.USERNAME)
    s=client();r=get(s,'/oidc/login')
    check('ASM3 redirects to actual Dex',r.status_code==303 and '/dex/auth?' in r.headers['Location'])
    r=s.get(r.headers['Location'],timeout=20)
    check('Dex offers LDAP login',r.status_code==200 and 'login' in r.text)
    match=re.search(r'<form[^>]*action="([^"]*)"',r.text)
    action=urljoin(r.url,html.unescape(match.group(1))) if match else r.url
    data=fields(r.text);data.update(login=admin,password=password)
    r=s.post(action,data=data,allow_redirects=True,timeout=20)
    # Redirects end on ASM3 enrollment (or an approval form if Dex configured otherwise).
    if '/approval' in r.url:
        action=urljoin(r.url,html.unescape(re.search(r'<form[^>]*action="([^"]*)"',r.text).group(1)))
        data=fields(r.text);data['approval']='approve';r=s.post(action,data=data,timeout=20)
    if not (r.status_code==200 and '/auth/mfa' in r.url):
        Path('/root/asm3-dex-browser-debug.html').write_text(str(r.status_code)+' '+r.url+'\n'+r.text)
    check('real Dex LDAP flow reaches ASM3 MFA',r.status_code==200 and '/auth/mfa' in r.url)
    username=re.search(r'Cuenta: <strong>([^<]+)</strong>',r.text).group(1)
    identity=dbo.query('SELECT * FROM users WHERE UserName=?',[username])[0]
    seed=re.search(r'<code id="setup-key">([^<]+)</code>',r.text).group(1)
    csrf=fields(r.text)['csrf']
    check('pending MFA blocks private POST before handler',s.post(base+'/config.js',data={'x':'y'},allow_redirects=False,timeout=20).status_code==303)
    check('pending MFA blocks private JSON',get(s,'/config.js').status_code==303)
    qr=get(s,'/auth/mfa/qr')
    check('enrollment QR has no-store and strict CSP',qr.status_code==200 and 'http://www.w3.org/2000/svg' in qr.text and 'no-store' in qr.headers['Cache-Control'] and "default-src 'none'" in qr.headers['Content-Security-Policy'])
    wrong=s.post(base+'/auth/mfa',data={'csrf':csrf,'code':'bad'},timeout=20)
    check('incorrect MFA code preserves unauthenticated challenge',wrong.status_code==200 and 'Código incorrecto' in wrong.text and get(s,'/main').status_code==303)
    code=ynh_mfa.totp(seed,int(time.time())//30)
    r=s.post(base+'/auth/mfa',data={'csrf':csrf,'code':code},allow_redirects=False,timeout=20)
    check('valid TOTP activates MFA and rotates into private session',r.status_code==303 and get(s,'/main').status_code==200)
    check('enrolled secret never available again as QR',get(s,'/auth/mfa/qr').status_code==403)
    # QR rejection resets session, so obtain another first factor through the portal.
    a=client();portal='https://'+setting('domain')+'/yunohost/portalapi/'
    a.post(portal+'login',data={'credentials':admin+':'+password},timeout=20)
    get(a,'/ynh_sso');page=otp_page(a);csrf=fields(page.text)['csrf']
    bad=a.post(base+'/auth/mfa',data={'csrf':'forged','code':code},allow_redirects=False,timeout=20)
    check('forged CSRF resets pending login',bad.status_code==403 and get(a,'/auth/mfa').status_code==403)
    get(a,'/ynh_sso');page=otp_page(a);csrf=fields(page.text)['csrf']
    native_seed=re.search(r'<code id="setup-key">([^<]+)</code>',page.text).group(1)
    native_code=ynh_mfa.totp(native_seed,int(time.time())//30)
    a.post(base+'/auth/mfa',data={'csrf':csrf,'code':native_code},allow_redirects=False,timeout=20)
    check('native SSO remains available with mandatory MFA',get(a,'/main').status_code==200)
    b=client();b.post(portal+'login',data={'credentials':admin+':'+password},timeout=20)
    get(b,'/ynh_sso');page=otp_page(b);csrf=fields(page.text)['csrf']
    replay=b.post(base+'/auth/mfa',data={'csrf':csrf,'code':native_code},timeout=20)
    check('TOTP replay across browsers rejected',replay.status_code==200 and 'ya utilizado' in replay.text)
    for _ in range(4):b.post(base+'/auth/mfa',data={'csrf':csrf,'code':'wrong'},timeout=20)
    locked=b.post(base+'/auth/mfa',data={'csrf':csrf,'code':ynh_mfa.totp(native_seed,int(time.time())//30+1)},timeout=20)
    check('persistent account lockout after five failed codes','Demasiados intentos' in locked.text)
    command('yunohost','app','action','run',app,'identity.recovery.reset_mfa','-a','reset_mfa_user='+admin)
    check('YunoHost root action invalidates active MFA sessions',get(a,'/main').status_code!=200)
    check('root reset invalidates pending enrollment',get(b,'/auth/mfa').status_code==403)
    # Social clients can be initialized without spending real cloud credentials.
    secret='TestSecret$(`literal`)"\\'+secrets.token_urlsafe(24)
    social=dict(cfg,google_login=True,google_client_id='fixture.apps.googleusercontent.com',google_client_secret=secret,
                github_login=True,github_client_id='fixture-github',github_client_secret=secret,
                microsoft_login=True,microsoft_client_id='11111111-1111-1111-1111-111111111111',microsoft_client_secret=secret,
                microsoft_tenant='22222222-2222-2222-2222-222222222222')
    panel(social)
    dexroot=Path(command('yunohost','app','setting','dex','install_dir'))
    head=yaml.safe_load((dexroot/'config.yaml.head').read_text())
    check('all three actual Dex cloud connectors load',all(any(c['id']=='asm3-'+app+'-'+p for c in head['connectors']) for p in ('google','github','microsoft')) and command('systemctl','is-active','dex')=='active')
    chooser=client();redirect=get(chooser,'/oidc/login')
    choice=chooser.get(redirect.headers['Location'],timeout=20)
    check('Dex presents all three social login choices',all(name+' ('+app+')' in choice.text for name in ('Google','Github','Microsoft')))
    links=[html.unescape(value) for value in re.findall(r'href="([^"]+)"',choice.text)]
    for provider in ('google','github','microsoft'):
        link=next(value for value in links if '/auth/asm3-'+app+'-'+provider+'?' in value)
        outbound=chooser.get(urljoin(choice.url,link),allow_redirects=False,timeout=20)
        location=outbound.headers.get('Location','')
        expected={'google':'accounts.google.com','github':'github.com','microsoft':'login.microsoftonline.com'}[provider]
        check('real '+provider+' connector emits cloud authorization redirect',outbound.status_code in (302,303) and urlsplit(location).hostname==expected)
        params=parse_qs(urlsplit(location).query)
        check(provider+' callback points to Dex',params.get('redirect_uri')==[issuer.rstrip('/')+'/callback'])
        if provider=='microsoft':
            check('Microsoft Graph permissions include user.read','user.read' in params.get('scope',[''])[0].lower().split())
    pid=command('systemctl','show','dex','--property=MainPID','--value')
    environ=Path('/proc/'+pid+'/environ').read_bytes().split(b'\0')
    check('systemd secrets preserve literal special characters',('ASM3_'+app.upper()+'_GOOGLE_CLIENT_SECRET='+secret).encode() in environ)
    show=command('yunohost','app','config','get',app,'--full','--output-as','json')
    check('panel getter never returns provider secrets',secret not in show and secret.replace('"','\\"') not in show)
    check('secret files are root only',all(p.stat().st_mode&0o777==0o600 and p.stat().st_uid==0 for p in (root/'identity_admin.json',dexroot/('asm3-'+app+'.env'))))
    # Blank secrets preserve previous credentials after editing another field.
    panel({'google_client_secret':'','github_client_secret':'','microsoft_client_secret':'','allowed_groups':'all_users'})
    check('blank panel passwords preserve previous credentials',json.loads((root/'identity_admin.json').read_text())['google_client_secret']==secret)
    old=(dexroot/'config.yaml.head').read_bytes()
    try:panel({'microsoft_tenant':'common'})
    except RuntimeError:pass
    check('invalid tenant cannot change active Dex config',(dexroot/'config.yaml.head').read_bytes()==old)
    before_files={p:p.read_bytes() for p in (root/'oidc.json',root/'identity_admin.json',dexroot/'config.yaml.head')}
    invalid_ca=Path('/root/asm3-invalid-ca.pem');invalid_ca.write_text('not a certificate')
    try:
        try:panel({'dex_ca_file':str(invalid_ca)})
        except RuntimeError:pass
        check('failed discovery rolls back configuration and keeps Dex working',all(p.read_bytes()==contents for p,contents in before_files.items()) and command('systemctl','is-active','dex')=='active')
    finally:invalid_ca.unlink(missing_ok=True)
    operation_logs=Path('/var/log/yunohost/operations')
    check('cloud secrets absent from YunoHost operation logs',all(secret not in p.read_text(errors='replace') for p in operation_logs.glob('*'+app+'*.log') if p not in prior_operation_logs))
    logs=command('journalctl','-u',app,'-u','dex','--no-pager')
    check('passwords and cloud secrets absent from service logs',password not in logs and secret not in logs)
    if args.lifecycle:
        before=json.loads((root/'identity_admin.json').read_text())
        backup='asm3-dex-'+secrets.token_hex(4)
        command('yunohost','backup','create','--name',backup,'--apps',app)
        command('yunohost','app','remove',app)
        check('uninstall detaches only ASM3 from shared Dex',not (dexroot/'config.yaml.d'/('asm3-'+app+'.yaml')).exists() and foreign.read_bytes()==foreign_bytes)
        command('yunohost','backup','restore',backup,'--apps',app,'--force')
        check('restore reconciles shared Dex and root-only credentials',json.loads((root/'identity_admin.json').read_text())==before and (root/'identity_admin.json').stat().st_mode&0o777==0o600 and (dexroot/'config.yaml.d'/('asm3-'+app+'.yaml')).exists())
        old_path=setting('path')
        command('yunohost','app','change-url',app,'--domain',setting('domain'),'--path',old_path+'-dex-test')
        generated=yaml.safe_load((dexroot/'config.yaml').read_text())
        registered=[c for c in generated['staticClients'] if c['id']==app][0]
        check('change URL updates registered Dex redirect',registered['redirectURIs']==[base+'-dex-test/oidc/callback'])
        command('yunohost','app','change-url',app,'--domain',setting('domain'),'--path',old_path)
        # A Dex upgrade-style event replays the same root hook without cloud secrets in argv.
        hook=Path('/etc/yunohost/hooks.d/post_app_upgrade')/('50-'+app)
        result=subprocess.run(['bash',str(hook)],env=dict(os.environ,YNH_APP_ID='dex',YNH_APP_INSTANCE_NAME='dex'),capture_output=True,text=True)
        check('registered Dex lifecycle hook reconciles successfully',result.returncode==0)
    panel({'dex_enabled':False})
    check('disable removes only owned shared Dex clients',not (dexroot/'config.yaml.d'/('asm3-'+app+'.yaml')).exists() and any(c['type']=='ldap' for c in yaml.safe_load((dexroot/'config.yaml.head').read_text())['connectors']))
    check('detach revokes the visitor grant it created','visitors' not in json.loads(command('yunohost','--output-as','json','user','permission','info',app+'.main'))['allowed'])
    if 'visitors' in original_main:
        command('yunohost','user','permission','add',app+'.main','visitors')
    check('other app client remains byte-for-byte intact',foreign.read_bytes()==foreign_bytes)
    foreign.unlink()
    command('systemctl','restart','dex')
    check('Dex service survives detachment',command('systemctl','is-active','dex')=='active')
    Path('/root/asm3-dex-results.json').write_text(json.dumps({'result':'success','checks':checks,'cloud_login':'not performed: no live cloud registrations; real connectors initialized with fixture credentials'},indent=2)+'\n')

if __name__=='__main__':main()
