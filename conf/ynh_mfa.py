"""Mandatory second factor for private browser access, including native/local SSO."""
import base64
import hashlib
import hmac
from html import escape
import io
import re
import secrets
import struct
import time
from urllib.parse import urlencode, quote


def enforced():
    import ynh_auth
    return ynh_auth.enabled()


def setup(dbo):
    dbo.execute('CREATE TABLE IF NOT EXISTS ynh_mfa_state (UserID INTEGER PRIMARY KEY, SecretHash CHAR(64) NOT NULL, Epoch INTEGER NOT NULL, LastCounter BIGINT NOT NULL, Failures INTEGER NOT NULL, LockUntil BIGINT NOT NULL)')


def seed_hash(user):
    return hashlib.sha256(str(user.get('OTPSECRET') or '').encode()).hexdigest()


def state(dbo, user):
    rows = dbo.query('SELECT * FROM ynh_mfa_state WHERE UserID=?', [user.ID])
    digest = seed_hash(user)
    if not rows:
        dbo.execute('INSERT INTO ynh_mfa_state (UserID,SecretHash,Epoch,LastCounter,Failures,LockUntil) VALUES (?,?,0,-1,0,0)', [user.ID,digest])
    elif rows[0].SECRETHASH != digest:
        dbo.execute('UPDATE ynh_mfa_state SET SecretHash=?,Epoch=Epoch+1,LastCounter=-1,Failures=0,LockUntil=0 WHERE UserID=?', [digest,user.ID])
    return dbo.query('SELECT * FROM ynh_mfa_state WHERE UserID=?', [user.ID])[0]


def totp(secret, counter):
    key = base64.b32decode(secret.upper(), casefold=True)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f'{(struct.unpack(">I",digest[offset:offset+4])[0]&0x7fffffff)%1000000:06d}'


def verify_code(secret, code, last_counter, now=None):
    if not re.fullmatch(r'[0-9]{6}', str(code)):
        return None
    counter = int(time.time() if now is None else now)//30
    for candidate in (counter+1,counter,counter-1):
        if candidate > last_counter and hmac.compare_digest(totp(secret,candidate),str(code)):
            return candidate
    return None


def proof_valid(dbo, session, user):
    proof = session.get('mfa_proof')
    if not proof or not user.get('ENABLETOTP'):
        return False
    row = state(dbo,user)
    return (proof.get('userid')==user.ID and proof.get('epoch')==row.EPOCH
            and proof.get('secret_hash')==seed_hash(user) and proof.get('until',0)>time.time())


def suspend(dbo, session, user):
    import ynh_auth as auth
    source = session.get('ynh_source','local')
    pending = {'userid':user.ID,'username':user.USERNAME,'source':source,
               'subject':session.get('ynh_subject',''),'uid':session.get('ynh_uid',''),
               'oidc':session.get('oidc_identity'),'password_hash':hashlib.sha256(str(user.PASSWORD).encode()).hexdigest(),
               'expires':time.time()+300,'csrf':secrets.token_urlsafe(32),'epoch':state(dbo,user).EPOCH}
    auth.reset_session(session)
    session.mfa_pending = pending


def pending_user(dbo, session):
    import ynh_auth as auth
    import asm3.users
    import web070 as web
    pending = session.get('mfa_pending')
    if not pending or pending['expires']<time.time():
        raise auth.AccessDenied('La comprobación ha caducado. Vuelve a iniciar sesión.')
    source = pending['source']
    if source=='sso':
        uid = web.ctx.env.get('asm3.ynh_user','')
        person = auth.directory_user(uid)
        if person['subject']!=pending['subject']:
            raise auth.AccessDenied('La identidad del portal ha cambiado.')
        user=auth.provision(dbo,person)
    elif source=='oidc':
        import ynh_oidc
        cfg=ynh_oidc.config()
        identity=ynh_oidc.checked_identity({'oidc_identity':pending['oidc']},cfg)
        user=ynh_oidc.provision(dbo,cfg,identity['claims'])
    elif source=='local':
        rows=dbo.query('SELECT * FROM users WHERE ID=?',[pending['userid']])
        if not rows:
            raise auth.AccessDenied('La cuenta ya no existe.')
        user=rows[0]
        if hashlib.sha256(str(user.PASSWORD).encode()).hexdigest()!=pending['password_hash']:
            raise auth.AccessDenied('La contraseña ha cambiado. Vuelve a iniciar sesión.')
    else:
        raise auth.AccessDenied('Origen de autenticación no válido.')
    if (user.ID!=pending['userid'] or user.DISABLELOGIN or not asm3.users.authenticate_ip(user,web.ctx.ip)
            or state(dbo,user).EPOCH!=pending['epoch']):
        raise auth.AccessDenied('La cuenta no tiene acceso.')
    return user


def complete(dbo,session,user,path):
    import ynh_auth as auth
    pending=session.mfa_pending
    row=state(dbo,user)
    until=time.time()+28800
    if pending['source']=='oidc':
        until=min(until,pending['oidc']['deadline'])
    proof={'userid':user.ID,'epoch':row.EPOCH,'secret_hash':seed_hash(user),'until':until}
    auth.start_session(dbo,session,user,{'subject':pending['subject'],'uid':pending['uid']},path)
    session.ynh_source=pending['source']
    session.force2fa=False
    if pending['source']=='oidc':
        session.oidc_identity=pending['oidc']
    elif pending['source']=='local':
        session.ynh_local_mode=True
    session.mfa_proof=proof


def check_submission(dbo,session,user,code,path):
    import ynh_auth as auth
    with auth._lock:
        # Reload under the lock: parallel enrollment cannot replace an activated seed.
        user=pending_user(dbo,session)
        row=state(dbo,user)
        now=time.time()
        if row.LOCKUNTIL>now:
            return 'Demasiados intentos. Espera cinco minutos antes de volver a intentarlo.'
        enrolling=not user.get('ENABLETOTP')
        seed=session.mfa_pending.get('enroll_seed') if enrolling else user.OTPSECRET
        if not seed:
            return 'Abre de nuevo la pantalla de verificación.'
        counter=verify_code(seed,code,-1 if enrolling else row.LASTCOUNTER)
        if counter is None:
            failures=row.FAILURES+1
            dbo.execute('UPDATE ynh_mfa_state SET Failures=?,LockUntil=? WHERE UserID=?',
                        [failures,int(now)+300 if failures>=5 else 0,user.ID])
            return 'Código incorrecto o ya utilizado. Introduce un código nuevo.'
        if enrolling:
            dbo.execute('UPDATE users SET OTPSecret=?,EnableTOTP=1 WHERE ID=?',[seed,user.ID])
            user=dbo.query('SELECT * FROM users WHERE ID=?',[user.ID])[0]
            row=state(dbo,user)
        dbo.execute('UPDATE ynh_mfa_state SET LastCounter=?,Failures=0,LockUntil=0 WHERE UserID=?',[counter,user.ID])
        complete(dbo,session,user,path)
        return None


def headers(content_type, nonce=None):
    import web070 as web
    web.header('Content-Type',content_type)
    web.header('Cache-Control','no-store, max-age=0')
    web.header('Pragma','no-cache')
    web.header('Referrer-Policy','no-referrer')
    web.header('X-Content-Type-Options','nosniff')
    style="'nonce-"+nonce+"'" if nonce else "'none'"
    web.header('Content-Security-Policy',"default-src 'none'; style-src "+style+"; img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")


def page(session,user,base,error=None):
    enrolling=not user.get('ENABLETOTP')
    pending=session.mfa_pending
    if enrolling and not pending.get('enroll_seed'):
        pending['enroll_seed']=base64.b32encode(secrets.token_bytes(20)).decode()
    title='Configura tu segundo factor' if enrolling else 'Verifica tu segundo factor'
    nonce=secrets.token_urlsafe(24)
    headers('text/html; charset=utf-8',nonce)
    setup_html=''
    if enrolling:
        setup_html=f'''<p>Escanea el QR con tu aplicación de autenticación y confirma el primer código.</p>
<figure><img src="{escape(base)}/auth/mfa/qr" alt="Código QR para configurar la aplicación de autenticación" width="256" height="256"><figcaption>Si no puedes escanearlo, introduce esta clave manualmente:</figcaption></figure>
<code id="setup-key">{escape(pending['enroll_seed'])}</code>'''
    error_html=f'<p id="error" role="alert">{escape(error)}</p>' if error else ''
    invalid=' aria-invalid="true"' if error else ''
    description='code-help error' if error else 'code-help'
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title} | Animal Shelter Manager</title>
<style nonce="{nonce}">body{{font-family:system-ui,sans-serif;background:#f4f6fa;color:#172438;line-height:1.6;margin:0}}main{{max-inline-size:36rem;margin:2rem auto;padding:1.5rem;background:white;border-radius:.75rem}}label{{display:block;font-weight:600}}input,button{{font:inherit;min-block-size:3rem;box-sizing:border-box;padding:.65rem}}input{{max-inline-size:100%;border:2px solid #52647c}}button{{display:block;margin-block:1rem;background:#154d89;color:white;border:0;border-radius:.3rem;cursor:pointer}}:focus-visible{{outline:3px solid #754500;outline-offset:3px}}code{{display:block;overflow-wrap:anywhere;padding:1rem;background:#edf1f6}}img{{max-inline-size:100%;block-size:auto}}figure{{margin-inline:0}}[role=alert]{{color:#9b1b14}}@media(max-width:40rem){{main{{margin:0;border-radius:0}}}}</style></head>
<body><main><h1>{title}</h1><p>Cuenta: <strong>{escape(user.USERNAME)}</strong>. El segundo factor es obligatorio para acceder a los datos.</p>
{setup_html}{error_html}<form action="{escape(base)}/auth/mfa" method="post"><input type="hidden" name="csrf" value="{escape(pending['csrf'])}">
<label for="code">Código de seis dígitos</label><p id="code-help">Usa el código actual de tu aplicación de autenticación. Puedes pegarlo completo.</p>
<input id="code" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{{6}}" minlength="6" maxlength="6" autocorrect="off" autocapitalize="off" spellcheck="false" aria-describedby="{description}"{invalid} required>
<button type="submit">Verificar y entrar</button></form><form action="{escape(base)}/auth/mfa" method="post"><input type="hidden" name="csrf" value="{escape(pending['csrf'])}"><input type="hidden" name="cancel" value="1"><button type="submit">Cancelar e iniciar sesión de nuevo</button></form>
<p>Si has perdido el segundo factor, solicita al administrador su restablecimiento desde YunoHost.</p></main></body></html>'''


def qr(session,user,base):
    import qrcode
    import qrcode.image.svg
    import ynh_auth as auth
    if user.get('ENABLETOTP') or not session.mfa_pending.get('enroll_seed'):
        raise auth.AccessDenied('No hay una configuración pendiente.')
    uri='otpauth://totp/'+quote('ASM3:'+user.USERNAME,safe='')+'?'+urlencode({'secret':session.mfa_pending['enroll_seed'],'issuer':'ASM3','digits':6,'period':30})
    output=io.BytesIO()
    qrcode.make(uri,image_factory=qrcode.image.svg.SvgPathImage).save(output)
    headers('image/svg+xml')
    return output.getvalue()


def reset_user(dbo,username):
    import ynh_auth as auth
    with auth._lock:
        users=dbo.query('SELECT * FROM users WHERE UserName=?',[username])
        if len(users)!=1:
            raise auth.AccessDenied('Usuario ASM3 no encontrado.')
        user=users[0]
        state(dbo,user)
        dbo.execute('UPDATE users SET EnableTOTP=0,OTPSecret=? WHERE ID=?',['',user.ID])
        dbo.execute('UPDATE ynh_mfa_state SET Epoch=Epoch+1,SecretHash=?,LastCounter=-1,Failures=0,LockUntil=0 WHERE UserID=?',[hashlib.sha256(b'').hexdigest(),user.ID])


def processor(session,path):
    import web070 as web
    import asm3.db
    import ynh_auth as auth
    from asm3.sitedefs import BASE_URL
    def run(handler):
        route=web.ctx.path
        if not enforced() or route.startswith('/static/') or route in auth.PUBLIC_PATHS:
            return handler()
        if route.startswith('/auth/mfa') or session.get('mfa_pending'):
            try:
                dbo=asm3.db.get_database();dbo.installpath=path
                user=pending_user(dbo,session)
                if route=='/auth/mfa/qr' and web.ctx.method=='GET':
                    return qr(session,user,BASE_URL)
                if route!='/auth/mfa':
                    raise web.seeother(BASE_URL+'/auth/mfa')
                error=None
                if web.ctx.method=='POST':
                    post=web.input()
                    token=post.get('csrf','')
                    if not isinstance(token,str) or not hmac.compare_digest(token.encode(),session.mfa_pending['csrf'].encode()):
                        raise auth.AccessDenied('La solicitud de verificación no es válida.')
                    if post.get('cancel')=='1':
                        auth.reset_session(session)
                        raise web.seeother(BASE_URL+'/login?local=1')
                    error=check_submission(dbo,session,user,post.get('code',''),path)
                    if error is None:
                        raise web.seeother(BASE_URL+'/main')
                elif web.ctx.method!='GET':
                    raise auth.AccessDenied('Método no permitido.')
                return page(session,user,BASE_URL,error)
            except auth.AccessDenied:
                auth.reset_session(session)
                headers('text/plain; charset=utf-8')
                raise web.forbidden('Verificación caducada o acceso denegado. Inicia sesión de nuevo.') from None
        if session.get('user'):
            dbo=asm3.db.get_database();dbo.installpath=path
            rows=dbo.query('SELECT * FROM users WHERE ID=?',[session.userid])
            if not rows or rows[0].DISABLELOGIN:
                auth.reset_session(session)
                raise web.forbidden('Cuenta deshabilitada.')
            user=rows[0]
            with auth._lock:
                valid=proof_valid(dbo,session,user)
                if valid:
                    pass
                elif session.get('mfa_proof'):
                    source=session.get('ynh_source')
                    auth.reset_session(session)
                    raise web.seeother(BASE_URL+('/oidc/login' if source=='oidc' else '/login'))
                else:
                    suspend(dbo,session,user)
            if valid:
                return handler()
            raise web.seeother(BASE_URL+'/auth/mfa')
        return handler()
    return run
