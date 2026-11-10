"""MFA browser helper, exclusively for disposable root integration labs."""
import re


def complete(session, base, dbo, check=lambda label,ok: None):
    import ynh_mfa
    r=session.get(base+'/main',allow_redirects=False,timeout=20)
    if r.status_code==200:return
    assert r.status_code==303 and r.headers['Location']==base+'/auth/mfa', (r.status_code,r.text[:150])
    r=session.get(base+'/auth/mfa',allow_redirects=False,timeout=20)
    assert r.status_code==200,r.text[:150]
    username=re.search(r'Cuenta: <strong>([^<]+)</strong>',r.text).group(1)
    import html
    username=html.unescape(username)
    user=dbo.query('SELECT * FROM users WHERE UserName=?',[username])[0]
    seed=re.search(r'<code id="setup-key">([^<]+)</code>',r.text)
    seed=seed.group(1) if seed else user.OTPSECRET
    csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    # Aísla los casos del laboratorio. En producción los accesos conservan el contador.
    dbo.execute('UPDATE ynh_mfa_state SET LastCounter=-1,Failures=0,LockUntil=0 WHERE UserID=?',[user.ID])
    r=session.post(base+'/auth/mfa',data={'csrf':csrf,'code':ynh_mfa.totp(seed,int(__import__('time').time())//30)},allow_redirects=False,timeout=20)
    assert r.status_code==303 and r.headers['Location']==base+'/main',(r.status_code,r.text[:150])
    check('mandatory MFA completed for '+username,True)
