#!/usr/bin/env python3
"""Diagnóstico ASM3: lectura del espejo, sin ejecutar sus fuentes."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import tomllib

from github_mirror import Mirror, SHA

REPOSITORY = 'asm3_ynh-private'
PUBLIC = 'Gente-del-Condado/asm3_ynh'


def inspect_archive(path):
    files, roots = {}, set()
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        if not members or len(members) > 10000 or sum(x.size for x in members) > 128 * 1024 * 1024:
            raise ValueError('Archivo fuera de límites')
        seen = set()
        for item in members:
            name = PurePosixPath(item.name)
            if (name.is_absolute() or '..' in name.parts or '.git' in name.parts
                    or '\\' in item.name or not name.parts
                    or not (item.isfile() or item.isdir()) or item.name in seen):
                raise ValueError('Ruta, enlace o entrada repetida no permitida')
            seen.add(item.name)
            roots.add(name.parts[0])
            if item.isfile():
                relative = PurePosixPath(*name.parts[1:]).as_posix()
                if relative == '.' or relative in files:
                    raise ValueError('Archivo sin ruta única')
                files[relative] = archive.extractfile(item).read()
        if len(roots) != 1:
            raise ValueError('Se exige una sola raíz')
    required = {'manifest.toml', 'upstream.lock.json', 'scripts/install', 'scripts/upgrade'}
    if not required <= files.keys():
        raise ValueError('Falta el paquete YunoHost')
    manifest = tomllib.loads(files['manifest.toml'].decode())
    lock = json.loads(files['upstream.lock.json'])
    source = manifest['resources']['sources']['main']
    if (manifest.get('id') != 'asm3' or manifest.get('packaging_format') != 2
            or lock.get('repository') != 'sheltermanager/asm3'
            or not SHA.fullmatch(lock.get('commit', ''))
            or not re.fullmatch(r'[0-9a-f]{64}', lock.get('sha256', ''))
            or source.get('url') != lock['url'] or source.get('sha256') != lock['sha256']
            or lock['url'] != 'https://codeload.github.com/sheltermanager/asm3/tar.gz/' + lock['commit']):
        raise ValueError('Manifiesto y origen fijado no coinciden')
    return {'version': manifest['version'], 'upstream_commit': lock['commit'],
            'upstream_sha256': lock['sha256'], 'tracked_files': len(files),
            'manifest_sha256': hashlib.sha256(files['manifest.toml']).hexdigest(),
            'lock_sha256': hashlib.sha256(files['upstream.lock.json']).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['download', 'check'])
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_REPOSITORY') != PUBLIC or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise ValueError('Solo se permite el diagnóstico desde el main público')
    receipt = args.archive.with_suffix('.json')
    if args.action == 'download':
        expected = os.environ.get('EXPECTED_SHA', '')
        if not SHA.fullmatch(expected):
            raise ValueError('Indica el SHA completo comprobado en Forgejo')
        reader = Mirror(REPOSITORY)
        if reader.branch() != expected:
            raise ValueError('El espejo no coincide con el SHA esperado de Forgejo')
        data = reader.archive(expected, limit=64 * 1024 * 1024).read()
        args.archive.write_bytes(data)
        receipt.write_text(json.dumps({'source_sha': expected, 'archive_sha256': hashlib.sha256(data).hexdigest()}))
    else:
        record = json.loads(receipt.read_text())
        if hashlib.sha256(args.archive.read_bytes()).hexdigest() != record['archive_sha256']:
            raise ValueError('Archivo alterado después de la descarga')
        record.update(inspect_archive(args.archive))
        print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
