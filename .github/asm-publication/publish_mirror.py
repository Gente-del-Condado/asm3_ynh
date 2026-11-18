#!/usr/bin/env python3
"""Exportación revisada de ASM3; el privado nunca ejecuta Actions."""
import argparse
import hashlib
import json
import os
import tomllib
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

from check_mirror import inspect_archive, PUBLIC, REPOSITORY
from github_mirror import Mirror, SHA

CONTROL = Path(__file__).resolve().parent


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def allowed():
    paths = (CONTROL / 'public-files.txt').read_text().splitlines()
    if len(paths) != len(set(paths)) or not paths:
        raise ValueError('Lista pública vacía o repetida')
    for name in paths:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or path.parts[0] in ('.git', '.github', '.publication'):
            raise ValueError('Ruta de publicación no autorizada')
    return paths


def output(name, value):
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write(name + '=' + str(value).lower() + '\n')


def inventory(root):
    root = Path(root)
    actual = []
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('No se publican enlaces')
        if path.is_file():
            actual.append(path.relative_to(root).as_posix())
    if set(actual) - set(allowed()):
        raise ValueError('Contenido ajeno a la lista pública revisada')
    if not {'manifest.toml', 'upstream.lock.json', 'scripts/install', 'scripts/upgrade'} <= set(actual):
        raise ValueError('Paquete público incompleto')
    return {name: {'sha256': hashlib.sha256((root / name).read_bytes()).hexdigest(),
                   'mode': 0o755 if (root / name).stat().st_mode & 0o111 else 0o644}
            for name in sorted(actual)}


def export(archive_path, destination):
    inspect_archive(archive_path)
    destination = Path(destination)
    destination.mkdir(parents=True)
    paths = set(allowed())
    with tarfile.open(archive_path, 'r:gz') as archive:
        for entry in archive.getmembers():
            name = PurePosixPath(*PurePosixPath(entry.name).parts[1:]).as_posix()
            if entry.isfile() and name.startswith(('conf/', 'doc/', 'docs/', 'scripts/', 'hooks/', 'patches/', 'tools/', 'tests/')) and name not in paths:
                raise ValueError('Archivo nuevo de distribución: revisar la lista pública antes de publicar')
            if not entry.isfile() or name not in paths:
                continue
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(entry).read())
            target.chmod(0o755 if entry.mode & 0o111 else 0o644)
    return inventory(destination)


def download(folder):
    folder.mkdir(parents=True)
    reader = Mirror(REPOSITORY)
    sha = reader.branch()
    archive = folder / 'main.tar.gz'
    archive.write_bytes(reader.archive(sha, limit=64 * 1024 * 1024).read())
    info = inspect_archive(archive)
    record = {'source_sha': sha, 'version': info['version']}
    (folder / 'source.json').write_text(json.dumps(record))
    previous = Path('.publication/asm3.json')
    previous = json.loads(previous.read_text()) if previous.exists() else {}
    output('changed', any(previous.get(key) != value for key, value in record.items()))
    print('FUENTE_ASM3:', sha, info['version'])


def prepare(folder, destination):
    record = json.loads((folder / 'source.json').read_text())
    record['main_files'] = export(folder / 'main.tar.gz', destination / 'main')
    (destination / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')


def verify(folder):
    record = json.loads((folder / 'receipt.json').read_text())
    if not SHA.fullmatch(record['source_sha']):
        raise ValueError('SHA inválido')
    # Los artefactos de Actions restauran todos los archivos como 0644.
    # Validar rutas y bytes antes de restaurar únicamente modos autorizados.
    for tree in ('main',):
        expected = record[tree + '_files']
        actual = inventory(folder / tree)
        if actual.keys() != expected.keys() or any(
                value.get('mode') not in (0o644, 0o755)
                or value.get('sha256') != actual[name]['sha256']
                for name, value in expected.items()):
            raise ValueError('Exportación alterada o permisos no autorizados')
        for name, value in expected.items():
            (folder / tree / name).chmod(value['mode'])
    if inventory(folder / 'main') != record['main_files']:
        raise ValueError('Exportación principal alterada')
    return record


def copy_files(source, root):
    for name in allowed():
        target, incoming = root / name, source / name
        if any(parent.is_symlink() for parent in (target, *target.parents)):
            raise ValueError('Destino enlazado')
        if incoming.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(incoming, target)
        elif target.exists():
            target.unlink()
    git(root, 'add', '--', *allowed())


def commit(root, message):
    if subprocess.run(['git', '-C', str(root), 'diff', '--cached', '--quiet']).returncode:
        git(root, '-c', 'user.name=github-actions[bot]',
            '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
            'commit', '-qm', message)


def publish(folder):
    record = verify(folder)
    subprocess.run(['gh', 'auth', 'setup-git'], check=True)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / 'public'
        subprocess.run(['git', 'clone', '--quiet', 'https://github.com/' + PUBLIC + '.git', str(root)], check=True)
        git(root, 'checkout', 'main')
        incoming = tomllib.loads((folder / 'main/manifest.toml').read_text())['version']
        current = tomllib.loads((root / 'manifest.toml').read_text())['version']
        if subprocess.run(['dpkg', '--compare-versions', incoming, 'lt', current]).returncode == 0:
            raise ValueError('No se retrocede la aplicación pública')
        copy_files(folder / 'main', root)
        receipt = root / '.publication/asm3.json'
        receipt.parent.mkdir(exist_ok=True)
        receipt.write_text(json.dumps(record, indent=2) + '\n')
        git(root, 'add', '.publication/asm3.json')
        commit(root, 'Publicar ASM3 desde espejo privado ' + record['source_sha'])
        git(root, 'push', 'origin', 'HEAD:main')
    print('ASM3_PUBLICADO:', record['source_sha'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['download', 'prepare', 'check', 'publish'])
    parser.add_argument('--source', type=Path, default=Path('download'))
    parser.add_argument('--prepared', type=Path, default=Path('prepared'))
    args = parser.parse_args()
    if os.environ.get('GITHUB_REPOSITORY') != PUBLIC or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise ValueError('Solo publica el repositorio público autorizado')
    if args.action == 'download':
        download(args.source)
    elif args.action == 'prepare':
        prepare(args.source, args.prepared)
    elif args.action == 'check':
        record = verify(args.prepared)
        reader = Mirror(REPOSITORY)
        if reader.branch() != record['source_sha']:
            raise ValueError('Las referencias privadas cambiaron; repetir desde el inicio')
    else:
        publish(args.prepared)


if __name__ == '__main__':
    main()
