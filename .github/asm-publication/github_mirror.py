#!/usr/bin/env python3
"""Lectura acotada de un espejo privado desde un runner público, sin historial."""
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

OWNER = 'Gente-del-Condado'
REPOSITORIES = {'asm3_ynh-private': 1463391767}
SHA = re.compile(r'[0-9a-f]{40}')


class ArchiveRedirect(urllib.request.HTTPRedirectHandler):
    """GitHub firma la URL de codeload; no se reenvía el Bearer a otro host."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if (parsed.scheme != 'https' or parsed.hostname not in {'api.github.com', 'codeload.github.com'}
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError('Redirección de archivo no autorizada')
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if redirected and parsed.hostname != urllib.parse.urlsplit(request.full_url).hostname:
            redirected.remove_header('Authorization')
        return redirected


class Mirror:
    def __init__(self, repository, token_variable='MIRROR_READ_TOKEN'):
        if repository not in REPOSITORIES:
            raise ValueError('Espejo no autorizado')
        self.repository = repository
        self.base = 'https://api.github.com/repos/' + OWNER + '/' + repository
        self.token = os.environ.get(token_variable, '')
        if not self.token:
            raise ValueError('Falta el token de lectura del espejo')
        self.verified = False

    def request(self, path, limit=2**20, archive=False):
        if path and (not path.startswith('/') or '\\' in path or '..' in path):
            raise ValueError('Ruta API no permitida')
        request = urllib.request.Request(self.base + path, headers={
            'Authorization': 'Bearer ' + self.token,
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'Gente-del-Condado-publication'})
        try:
            with urllib.request.build_opener(ArchiveRedirect()).open(request, timeout=120) as response:
                if not archive and urllib.parse.urlsplit(response.url).hostname != 'api.github.com':
                    raise ValueError('Respuesta API fuera de GitHub')
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ValueError('Respuesta del espejo demasiado grande')
                if not archive and 'json' not in response.headers.get('Content-Type', ''):
                    raise ValueError('Respuesta API no válida')
                return data if archive else json.loads(data)
        except urllib.error.HTTPError as error:
            raise ValueError('Lectura del espejo rechazada (HTTP ' + str(error.code) + ')') from None
        except urllib.error.URLError:
            raise ValueError('No se pudo consultar el espejo') from None

    def verify(self):
        if not self.verified:
            metadata = self.request('')
            if (metadata.get('id') != REPOSITORIES[self.repository]
                    or metadata.get('full_name') != OWNER + '/' + self.repository
                    or metadata.get('private') is not True):
                raise ValueError('El origen no es el espejo privado esperado')
            self.verified = True

    def branch(self, name='main'):
        if name != 'main' and not re.fullmatch(r'codex/[a-z0-9-]+', name):
            raise ValueError('Rama no autorizada')
        self.verify()
        document = self.request('/branches/' + urllib.parse.quote(name, safe=''))
        sha = document.get('commit', {}).get('sha', '')
        if document.get('name') != name or not SHA.fullmatch(sha):
            raise ValueError('Referencia de rama no válida')
        return sha

    def tag(self, name):
        if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', name):
            raise ValueError('Etiqueta estable no válida')
        self.verify()
        value = self.request('/git/ref/tags/' + name).get('object', {})
        for _ in range(8):
            sha = value.get('sha', '')
            if not SHA.fullmatch(sha):
                raise ValueError('Referencia de etiqueta no válida')
            if value.get('type') == 'commit':
                return sha
            if value.get('type') != 'tag':
                break
            value = self.request('/git/tags/' + sha).get('object', {})
        raise ValueError('La etiqueta no resuelve a un commit')

    def archive(self, sha, limit=2**30):
        if not SHA.fullmatch(sha):
            raise ValueError('Commit no válido')
        self.verify()
        return io.BytesIO(self.request('/tarball/' + sha, limit=limit, archive=True))
