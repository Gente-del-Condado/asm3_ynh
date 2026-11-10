#!/usr/bin/env python3
"""Root-only YunoHost configuration: shared Dex integration and mandatory MFA reset."""
import argparse
import fcntl
import grp
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import subprocess
import sys
import tempfile
import time
import tomllib
from urllib.parse import urlsplit

import yaml

DEFAULTS={'dex_enabled':False,'dex_instance':'dex','dex_ldap_login':True,'google_login':False,
          'google_client_id':'','google_client_secret':'','github_login':False,'github_client_id':'',
          'github_client_secret':'','github_org':'','github_team':'','microsoft_login':False,
          'microsoft_client_id':'','microsoft_client_secret':'','microsoft_tenant':'',
          'allowed_emails':'','allowed_groups':'','allowed_subjects':'','dex_ca_file':'',
          'allow_external_entry':True}
SECRETS={k for k in DEFAULTS if k.endswith('_secret')}
BOOLEANS={k for k,v in DEFAULTS.items() if isinstance(v,bool)}


class ConfigError(Exception):
    pass


def command(*args, optional=False):
    result=subprocess.run(args,capture_output=True,text=True)
    if result.returncode and not optional:
        raise ConfigError('No se pudo completar una operación de YunoHost/Dex.')
    return result.stdout.strip() if result.returncode==0 else ''


def settings(app):
    path=Path('/etc/yunohost/apps')/app/'settings.yml'
    return yaml.safe_load(path.read_text())


def atomic(path, data, mode=0o600, gid=0, uid=0):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.asm3-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as output:
            output.write(data);output.flush();os.fsync(output.fileno())
            os.fchmod(output.fileno(),mode);os.fchown(output.fileno(),uid,gid)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


class Transaction:
    def __init__(self):self.original={}
    def remember(self,path):
        path=Path(path)
        if path not in self.original:
            info=path.stat() if path.exists() else None
            self.original[path]=(path.read_bytes(),info.st_mode&0o777,info.st_gid,info.st_uid) if info else None
    def write(self,path,data,mode=0o600,gid=0):
        self.remember(path);atomic(path,data,mode,gid)
    def delete(self,path):
        self.remember(path);Path(path).unlink(missing_ok=True)
    def rollback(self):
        for path,value in reversed(list(self.original.items())):
            if value is None:path.unlink(missing_ok=True)
            else:atomic(path,*value)


def load_state(root):
    path=root/'identity_admin.json'
    data=json.loads(path.read_text()) if path.exists() else {}
    return dict(DEFAULTS,**data)


def entries(value):
    values=[v.strip() for v in re.split('[,\n]',value) if v.strip()]
    if len(values)>1000 or any(len(v)>255 or any(ord(c)<32 for c in v) for v in values):
        raise ConfigError('La lista de usuarios/grupos no es válida.')
    return list(dict.fromkeys(values))


def candidate(previous,env):
    data=dict(previous)
    for key in DEFAULTS:
        if key not in env:continue
        value=env[key]
        if key in BOOLEANS:
            if value.lower() not in ('true','false','1','0','yes','no'):
                raise ConfigError('Valor booleano no válido.')
            data[key]=value.lower() in ('true','1','yes')
        elif key in SECRETS and value=='':
            continue  # Blank password fields retain the existing protected secret.
        else:
            if any(ord(c)<32 and c not in '\n\t' for c in value) or len(value)>16384:
                raise ConfigError('Valor de configuración no válido.')
            data[key]=value.strip() if key not in SECRETS else value
    if not re.fullmatch(r'dex(?:__\d+)?',data['dex_instance']):
        raise ConfigError('Selecciona una instancia Dex instalada.')
    for key in ('allowed_emails','allowed_groups','allowed_subjects'):entries(data[key])
    for email in entries(data['allowed_emails']):
        if not re.fullmatch(r'[^\s@,<>]+@[^\s@,<>]+\.[^\s@,<>]+',email):
            raise ConfigError('Introduce direcciones de correo completas y verificadas.')
    for provider in ('google','github','microsoft'):
        if data[provider+'_login']:
            for suffix in ('_client_id','_client_secret'):
                value=data[provider+suffix]
                if not value or any(ord(c)<32 for c in value):
                    raise ConfigError('Completa el cliente y secreto de cada proveedor activado.')
    if data['github_team'] and not data['github_org']:
        raise ConfigError('Indica la organización GitHub del equipo permitido.')
    if data['microsoft_login'] and not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',data['microsoft_tenant']):
        raise ConfigError('Usa el UUID concreto del tenant Microsoft.')
    if data['dex_enabled'] and not any((data['dex_ldap_login'],data['google_login'],data['github_login'],data['microsoft_login'])):
        raise ConfigError('Activa al menos un método de acceso en Dex.')
    if data['dex_ca_file'] and (not Path(data['dex_ca_file']).is_absolute() or not Path(data['dex_ca_file']).is_file()):
        raise ConfigError('El certificado de CA debe ser un archivo PEM absoluto existente.')
    return data


def render_connectors(app,data,head):
    prefix='asm3-'+app+'-'
    connectors=[c for c in head.get('connectors',[]) if not c.get('id','').startswith(prefix)]
    allowed=[]
    if data['dex_ldap_login']:
        allowed=[c['id'] for c in connectors if c.get('type')=='ldap']
        if not allowed:raise ConfigError('La instancia Dex no tiene un conector LDAP.')
    env={}
    namespace='ASM3_'+app.upper()+'_'
    for provider in ('google','github','microsoft'):
        if not data[provider+'_login']:continue
        ident=prefix+provider
        config={'clientID':'$'+namespace+provider.upper()+'_CLIENT_ID',
                'clientSecret':'$'+namespace+provider.upper()+'_CLIENT_SECRET',
                'redirectURI':head['issuer'].rstrip('/')+'/callback'}
        env[namespace+provider.upper()+'_CLIENT_ID']=data[provider+'_client_id']
        env[namespace+provider.upper()+'_CLIENT_SECRET']=data[provider+'_client_secret']
        if provider=='github':
            config['useLoginAsID']=False
            if data['github_org']:
                org={'name':data['github_org']}
                if data['github_team']:org['teams']=[data['github_team']]
                config['orgs']=[org]
        elif provider=='microsoft':
            # El conector Microsoft de Dex usa Graph /me y necesita su permiso predeterminado user.read.
            config.update(tenant=data['microsoft_tenant'])
        connectors.append({'type':provider,'id':ident,'name':provider.title()+' ('+app+')','config':config})
        allowed.append(ident)
    return dict(head,connectors=connectors),env,allowed


def dump_head(head):
    # El generador oficial concatena las listas de clientes tras esta última clave.
    data=dict(head)
    clients=data.pop("staticClients",None)
    return (yaml.safe_dump(data,sort_keys=False)+"staticClients:\n"+(yaml.safe_dump(clients,sort_keys=False) if clients else "")).encode()


def env_file(values):
    # EnvironmentFile de systemd conserva el signo $ literalmente.
    return ''.join(key+'="'+value.replace('\\','\\\\').replace('"','\\"')+'"\n' for key,value in sorted(values.items())).encode()


def dex_paths(app,data):
    instance=data['dex_instance']
    meta=Path('/etc/yunohost/apps')/instance/'manifest.toml'
    if not meta.exists() or tomllib.loads(meta.read_text()).get('id')!='dex':
        raise ConfigError('Instala Dex desde el catálogo antes de activar esta integración.')
    values=settings(instance)
    root=Path(values['install_dir'])
    return instance,root,grp.getgrnam(instance).gr_gid


def base_url(root):
    for line in (root/'asm3.conf').read_text().splitlines():
        if line.startswith('base_url = '):return line.split('=',1)[1].strip().rstrip('/')
    raise ConfigError('No se encuentra la URL de ASM3.')


def stop_monitor(instance):
    active=command('systemctl','is-active',instance+'-monitor.path',optional=True)=='active'
    command('systemctl','stop',instance+'-monitor.path',instance+'-monitor.service',optional=True)
    return active


def wait_provider(cfg):
    import ynh_oidc
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        try:return ynh_oidc.discovery(cfg)
        except Exception:time.sleep(.5)
    raise ConfigError('Dex no responde con discovery válido; se restaura la configuración anterior.')


def configure(app,root,data,previous,detach=False,reconcile=False):
    import ynh_oidc
    tx=Transaction();instance=None;monitor=False;visitor_delta=0
    owner=pwd.getpwnam(app).pw_gid
    # Si Dex no está gestionado aquí, conserva la configuración genérica de OIDC.
    if not data['dex_enabled'] and not previous.get('dex_enabled'):
        atomic(root/'identity_admin.json',(json.dumps(data,indent=2)+'\n').encode())
        return
    if previous.get('dex_enabled') and data['dex_instance']!=previous['dex_instance']:
        raise ConfigError('Desactiva la integración antes de cambiar de instancia Dex.')
    if not (Path('/etc/yunohost/apps')/data['dex_instance']/'manifest.toml').exists():
        if detach:
            (Path('/etc/systemd/system')/(data['dex_instance']+'.service.d')/('asm3-'+app+'.conf')).unlink(missing_ok=True)
            command('systemctl','daemon-reload',optional=True)
            return
        if reconcile:
            return  # Restore Dex first to reactivate external login; native/local MFA remains available.
    try:
        instance,dexroot,dexgid=dex_paths(app,data)
        head_path=dexroot/'config.yaml.head'
        head=yaml.safe_load(head_path.read_text())
        ynh_oidc.https_url(head['issuer'])
        if urlsplit(head['issuer']).query:raise ConfigError('El issuer Dex no es válido.')
        # Conserva los ajustes globales y conectores gestionados por otras aplicaciones.
        fragment=dexroot/'config.yaml.d'/('asm3-'+app+'.yaml')
        environment=dexroot/('asm3-'+app+'.env')
        dropin=Path('/etc/systemd/system')/(instance+'.service.d')/('asm3-'+app+'.conf')
        prefix='asm3-'+app+'-'
        if data['dex_enabled'] and not detach:
            rendered,env,connectors=render_connectors(app,data,head)
            oidc_path=root/'oidc.json'
            current=json.loads(oidc_path.read_text())
            if not previous.get('dex_enabled'):
                data['prior_oidc']=current
            secret=previous.get('dex_client_secret') or secrets.token_urlsafe(48)
            data['dex_client_secret']=secret
            env['ASM3_'+app.upper()+'_OIDC_SECRET']=secret
            client={'id':app,'name':'Animal Shelter Manager ('+app+')',
                    'secretEnv':'ASM3_'+app.upper()+'_OIDC_SECRET',
                    'redirectURIs':[base_url(root)+'/oidc/callback']}
            cfg={'enabled':True,'issuer':head['issuer'],'client_id':app,'client_secret':secret,
                 'id_token_signing_alg':'RS256','token_endpoint_auth_method':'client_secret_post',
                 'scopes':['openid','profile','email','federated:id']+(['groups'] if entries(data['allowed_groups']) else []),
                 'allowed_subjects':entries(data['allowed_subjects']),'allowed_groups':entries(data['allowed_groups']),
                 'allowed_emails':entries(data['allowed_emails']),'allowed_connectors':connectors,
                 'groups_claim':'groups','ldap_links':{},'session_max_age':3600,'managed_by':'asm3-dex'}
            if data['dex_ca_file']:
                tx.write(root/'identity-ca.pem',Path(data['dex_ca_file']).read_bytes(),0o640,owner)
                cfg['ca_bundle']=str(root/'identity-ca.pem')
            monitor=stop_monitor(instance)
            tx.write(environment,env_file(env))
            tx.write(dropin,('[Service]\nEnvironmentFile='+str(environment)+'\n').encode(),0o644)
            tx.write(fragment,('\n'+yaml.safe_dump([client],sort_keys=False)).encode(),0o640,dexgid)
            tx.write(head_path,dump_head(rendered),0o640,dexgid)
            command('systemctl','daemon-reload')
            command('systemctl','restart',instance)
            wait_provider(cfg)
            tx.write(oidc_path,(json.dumps(cfg,indent=2)+'\n').encode(),0o640,owner)
            if data['allow_external_entry']:
                info=json.loads(command('yunohost','--output-as','json','user','permission','info',app+'.main'))
                if 'visitors' not in info['allowed']:
                    command('yunohost','user','permission','add',app+'.main','visitors')
                    data['added_visitors']=True
                    visitor_delta=1
            elif data.pop('added_visitors',False):
                command('yunohost','user','permission','remove',app+'.main','visitors')
                visitor_delta=-1
            data.pop('last_error',None)
        else:
            rendered=dict(head,connectors=[c for c in head.get('connectors',[]) if not c.get('id','').startswith(prefix)])
            monitor=stop_monitor(instance)
            tx.delete(fragment);tx.delete(environment);tx.delete(dropin)
            tx.write(head_path,dump_head(rendered),0o640,dexgid)
            command('systemctl','daemon-reload');command('systemctl','restart',instance)
            if not detach:
                restored=data.pop('prior_oidc',{'enabled':False})
                tx.write(root/'oidc.json',(json.dumps(restored,indent=2)+'\n').encode(),0o640,owner)
                if data.pop('added_visitors',False):
                    command('yunohost','user','permission','remove',app+'.main','visitors')
                    visitor_delta=-1
        if not detach:
            tx.write(root/'identity_admin.json',(json.dumps(data,indent=2)+'\n').encode())
    except Exception:
        tx.rollback()
        if visitor_delta:
            command("yunohost","user","permission","remove" if visitor_delta>0 else "add",app+".main","visitors",optional=True)
        if instance:
            command('systemctl','daemon-reload',optional=True)
            command('systemctl','restart',instance,optional=True)
        raise
    finally:
        if instance and monitor:command('systemctl','start',instance+'-monitor.path',optional=True)


def display(root,state):
    result={key:('' if key in SECRETS else state[key]) for key in DEFAULTS}
    callbacks='ASM3: '+base_url(root)+'/oidc/callback'
    try:
        _,dexroot,_=dex_paths('asm3',state)
        issuer=yaml.safe_load((dexroot/'config.yaml.head').read_text())['issuer']
        callbacks+=' | Google/GitHub/Microsoft: '+issuer.rstrip('/')+'/callback'
    except Exception:
        callbacks+=' | Instala Dex desde el catálogo y selecciona su identificador.'
    result['identity_status']={'ask':{'es':callbacks,'en':callbacks},'style':'info'}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('show','apply','reconcile','detach','reset_mfa'))
    parser.add_argument('--app',required=True)
    parser.add_argument('--install-dir',type=Path)
    args=parser.parse_args()
    if os.geteuid()!=0 or not re.fullmatch(r'asm3(?:__\d+)?',args.app):
        raise ConfigError('Requiere administración root de una instancia ASM3.')
    root=args.install_dir or Path(settings(args.app)['install_dir'])
    os.environ['ASM3_CONF']=str(root/'asm3.conf')
    sys.path.insert(0,str(root/'upstream/src'))
    state=load_state(root)
    if args.action=='show':
        print(json.dumps(display(root,state)))
        return
    with open('/run/lock/asm3-identity.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if args.action=='reset_mfa':
            username=os.environ.get('reset_mfa_user','').strip()
            if not username or len(username)>100 or any(ord(c)<32 for c in username):
                raise ConfigError('Indica el nombre exacto del usuario ASM3.')
            import asm3.db,ynh_mfa
            # Detén el proceso web para que el reinicio del factor no compita con accesos en curso.
            command('systemctl','stop',args.app)
            try:
                ynh_mfa.reset_user(asm3.db.get_database(),username)
            finally:
                command('systemctl','start',args.app)
                import requests
                with requests.Session() as client:
                    client.trust_env=False
                    for _ in range(40):
                        try:
                            if client.get('http://127.0.0.1:'+str(settings(args.app)['port'])+'/_ynh_health',timeout=1).status_code==200:
                                break
                        except requests.RequestException:
                            pass
                        time.sleep(.25)
                    else:
                        raise ConfigError('MFA restablecido, pero ASM3 no respondió a la comprobación de salud.')
        elif args.action=='apply':
            data=candidate(state,os.environ)
            configure(args.app,root,data,state)
        elif args.action=='detach':
            if state.get('dex_enabled'):
                configure(args.app,root,state,state,detach=True)
        elif args.action=='reconcile' and state.get('dex_enabled'):
            configure(args.app,root,state,state,reconcile=True)
    print('{}')


if __name__=='__main__':
    try:main()
    except Exception as error:
        # Muestra solo mensajes de validación predefinidos para proteger datos del proveedor.
        message=str(error) if isinstance(error,ConfigError) else 'La integración no se aplicó. Comprueba Dex y los datos introducidos; la configuración previa se conserva.'
        print(json.dumps({'validation_errors':{'dex_enabled':message}}))
        if len(sys.argv)>1 and sys.argv[1]=='apply':raise SystemExit(0)
        print('Operación de identidad rechazada; no se han registrado credenciales.',file=sys.stderr)
        raise SystemExit(1)
