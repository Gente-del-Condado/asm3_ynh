"""Ephemeral HTTPS OIDC provider for protocol integration tests, never deployed."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import ssl
import tempfile
import threading
from urllib.parse import parse_qs, unquote_plus, urlencode, urlsplit


class Provider:
    def __init__(self):
        import jwt
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        self.temp = tempfile.TemporaryDirectory(prefix='asm3-oidc-provider-')
        root = Path(self.temp.name)
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(self.key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
                .not_valid_after(now+timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(self.key, hashes.SHA256()))
        self.ca = cert.public_bytes(serialization.Encoding.PEM)
        certfile, keyfile = root/'ca.pem', root/'key.pem'
        certfile.write_bytes(self.ca)
        keyfile.write_bytes(self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
        self.ca_file = str(certfile)
        self.secret = secrets.token_urlsafe(32) + ': +'
        self.client_id = 'asm3-oidc-test'
        self.subject = 'external-subject'
        self.name = 'External OIDC User'
        self.email = 'external@example.test'
        self.groups = ['asm3-staff']
        self.scenario = ''
        self.algorithm = 'RS256'
        self.codes = {}
        self.exchanges = []
        self.tokens = []
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwk.update(kid='fixture-key', use='sig', alg='RS256')
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, data, status=200):
                content = json.dumps(data).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def redirect(self, url):
                self.send_response(302)
                self.send_header('Location', url)
                self.send_header('Content-Length', '0')
                self.end_headers()

            def do_GET(self):
                url = urlsplit(self.path)
                if url.path.endswith('/.well-known/openid-configuration'):
                    self.answer({'issuer': provider.issuer, 'authorization_endpoint': provider.issuer+'/auth',
                                 'token_endpoint': provider.issuer+'/token', 'jwks_uri': provider.issuer+'/keys',
                                 'end_session_endpoint': provider.issuer+'/logout', 'response_types_supported': ['code'],
                                 'id_token_signing_alg_values_supported': ['RS256', 'RS512'], 'code_challenge_methods_supported': ['S256'],
                                 'token_endpoint_auth_methods_supported': ['client_secret_basic', 'client_secret_post', 'none']})
                elif url.path.endswith('/keys'):
                    self.answer({'keys': [dict(provider.jwk, alg=provider.algorithm)]})
                elif url.path.endswith('/auth'):
                    q = {k: v[0] for k, v in parse_qs(url.query).items()}
                    if q.get('client_id') != provider.client_id or q.get('code_challenge_method') != 'S256':
                        return self.answer({'error': 'invalid_request'}, 400)
                    code = secrets.token_urlsafe(24)
                    provider.codes[code] = q
                    self.redirect(q['redirect_uri']+'?'+urlencode({'state': q['state'], 'code': code, 'iss': provider.issuer}))
                elif url.path.endswith('/logout'):
                    q = {k: v[0] for k, v in parse_qs(url.query).items()}
                    self.redirect(q['post_logout_redirect_uri']+'?'+urlencode({'state': q['state']}))
                else:
                    self.answer({'error': 'not_found'}, 404)

            def do_POST(self):
                import jwt
                import time
                length = int(self.headers.get('Content-Length', '0'))
                q = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
                if provider.scenario == 'token_error':
                    return self.answer({'error': 'invalid_grant', 'error_description': 'SENSITIVE_PROVIDER_ERROR'}, 400)
                authorization = self.headers.get('Authorization', '')
                if authorization.startswith('Basic '):
                    parts = base64.b64decode(authorization[6:]).decode().split(':', 1)
                    valid_client = [unquote_plus(p) for p in parts] == [provider.client_id, provider.secret]
                else:
                    valid_client = q.get('client_id') == provider.client_id and q.get('client_secret', provider.secret) == provider.secret
                tx = provider.codes.pop(q.get('code'), None)
                challenge = base64.urlsafe_b64encode(hashlib.sha256(q.get('code_verifier', '').encode()).digest()).rstrip(b'=').decode()
                if not valid_client or not tx or q.get('redirect_uri') != tx['redirect_uri'] or challenge != tx['code_challenge']:
                    return self.answer({'error': 'invalid_grant'}, 400)
                provider.exchanges.append({'pkce': True, 'redirect_uri': q['redirect_uri']})
                claims = {'iss': provider.issuer, 'sub': provider.subject, 'aud': provider.client_id,
                          'iat': int(time.time()), 'exp': int(time.time())+600, 'nonce': tx['nonce'],
                          'name': provider.name, 'email': provider.email, 'email_verified': True, 'groups': provider.groups}
                cases = {'bad_nonce': {'nonce': 'wrong'}, 'bad_audience': {'aud': 'other-client'},
                         'bad_issuer': {'iss': 'https://attacker.invalid'}, 'expired': {'exp': int(time.time())-60}}
                claims.update(cases.get(provider.scenario, {}))
                if provider.scenario == 'short_lived':
                    claims['exp'] = int(time.time()) + 6
                if provider.scenario == 'unsigned':
                    token = jwt.encode(claims, None, algorithm='none')
                else:
                    token = jwt.encode(claims, provider.key, algorithm=provider.algorithm, headers={'kid': 'fixture-key'})
                provider.tokens.append(token)
                self.answer({'id_token': token, 'access_token': 'ACCESS_TOKEN_MUST_NOT_LEAK',
                             'refresh_token': 'REFRESH_TOKEN_MUST_NOT_LEAK', 'token_type': 'Bearer', 'expires_in': 600})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.issuer = 'https://localhost:' + str(self.server.server_port) + '/dex'
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(certfile, keyfile)
        self.server.socket = tls.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()
