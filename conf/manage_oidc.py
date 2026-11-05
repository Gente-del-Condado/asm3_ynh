#!/usr/bin/env python3
"""Validate and atomically apply root-owned OIDC JSON; secrets never enter argv/logs."""
import argparse
import http.client
import time
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', default='asm3')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch(r'asm3(?:__\d+)?', args.app):
        raise ValueError('Root and a valid application ID are required')
    root = Path(subprocess.check_output(['yunohost', 'app', 'setting', args.app, 'install_dir'], text=True).strip())
    os.environ['ASM3_CONF'] = str(root / 'asm3.conf')
    sys.path.insert(0, str(root / 'upstream/src'))
    import ynh_oidc
    cfg = ynh_oidc.config(args.config)
    if cfg.get('enabled'):
        ynh_oidc.discovery(cfg)
    if args.validate_only:
        print('OIDC configuration and provider discovery: OK')
        return
    content = json.dumps(json.loads(args.config.read_text()), indent=2) + '\n'
    destination = root / 'oidc.json'
    previous = destination.read_bytes()
    gid = pwd.getpwnam(args.app).pw_gid

    def write(data):
        fd, name = tempfile.mkstemp(prefix='.oidc-', dir=root)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
                os.fchmod(output.fileno(), 0o640)
                os.fchown(output.fileno(), 0, gid)
            os.replace(name, destination)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    write(content.encode())
    restarted = subprocess.run(['systemctl', 'restart', args.app], capture_output=True)
    ready = False
    if restarted.returncode == 0:
        port = int(subprocess.check_output(['yunohost', 'app', 'setting', args.app, 'port'], text=True).strip())
        for _ in range(60):
            try:
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
                connection.request('GET', '/_ynh_health')
                ready = connection.getresponse().status == 200
                connection.close()
                if ready:
                    break
            except OSError:
                pass
            time.sleep(0.25)
    if not ready:
        write(previous)
        subprocess.run(['systemctl', 'restart', args.app], capture_output=True)
        raise RuntimeError('Service restart failed; previous configuration restored')
    print('OIDC configuration applied; native SSO and LDAP remain available')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('OIDC configuration rejected; no credentials were logged', file=sys.stderr)
        raise SystemExit(1)
