#!/usr/bin/env python3
"""Run real ASM3 install, HTTP login, migration and SQL restore in a temporary MariaDB.

Requires MariaDB binaries and ASM3's Python dependencies. Never uses the host DB.
--archive accepts an already downloaded upstream tarball (SHA-256 still verified).
"""
import argparse
import hashlib
import getpass
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(check, process, log):
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError(log.read_text())
        try:
            if check():
                return
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(0.25)
    raise RuntimeError("Service timeout: " + log.read_text())


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    lock = json.loads((ROOT / "upstream.lock.json").read_text())
    with tempfile.TemporaryDirectory(prefix="asm3-smoke-") as temp:
        work = Path(temp)
        archive = args.archive or work / "source.tar.gz"
        if not args.archive:
            with urllib.request.urlopen(lock["url"], timeout=120) as response, archive.open("wb") as out:
                shutil.copyfileobj(response, out)
        digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
        assert digest == lock["sha256"], "Upstream archive checksum mismatch"
        install = work / "app"
        upstream = install / "upstream"
        upstream.mkdir(parents=True)
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            top = members[0].name.split("/")[0]
            tar.extractall(work / "unpack", filter="data")
        shutil.copytree(work / "unpack" / top, upstream, dirs_exist_ok=True)
        for patch in sorted((ROOT / "patches/main").glob("*.patch")):
            subprocess.run(["patch", "--batch", "--forward", "--strip=1", "--input", str(patch)], cwd=upstream, check=True)
        shutil.copytree(ROOT / "conf", install / "ynh")
        for module in ("ynh_auth", "ynh_oidc"):
            shutil.copy(ROOT / f"conf/{module}.py", upstream / f"src/{module}.py")
        cache = work / "cache"
        cache.mkdir()
        sql_dir = work / "mysql"
        db_socket = work / "mysql.sock"
        db_port = free_port()
        db_log = work / "mysql.log"
        subprocess.run(["mariadb-install-db", "--no-defaults", f"--datadir={sql_dir}", "--auth-root-authentication-method=normal", "--skip-test-db"], check=True, stdout=subprocess.DEVNULL)
        db = web = None
        try:
            with db_log.open("w") as log:
                db = subprocess.Popen(["mariadbd", "--no-defaults", f"--user={getpass.getuser()}", f"--datadir={sql_dir}", f"--socket={db_socket}",
                                       f"--pid-file={work / 'mysql.pid'}", "--bind-address=127.0.0.1", f"--port={db_port}",
                                       "--innodb-buffer-pool-size=64M"], stdout=log, stderr=log)
            cli = ["mariadb", "--no-defaults", f"--socket={db_socket}", "-uroot", "--batch", "--skip-column-names"]

            def ready():
                return subprocess.run([*cli, "-e", "SELECT 1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

            wait_for(ready, db, db_log)
            db_password = secrets.token_hex(20)
            subprocess.run(cli, input=f"CREATE DATABASE asm3_smoke; CREATE USER 'asm3test'@'127.0.0.1' IDENTIFIED BY '{db_password}'; GRANT ALL ON asm3_smoke.* TO 'asm3test'@'127.0.0.1';", text=True, check=True)
            config = install / "asm3.conf"
            config.write_text(f"db_type = MYSQL\ndb_host = 127.0.0.1\ndb_port = {db_port}\ndb_username = asm3test\ndb_password = {db_password}\ndb_name = asm3_smoke\nlocale = es\nlog_location = stderr\nlog_debug = false\ndisk_cache = {cache}\nsession_secure_cookie = true\n")
            env = {**os.environ, "ASM3_CONF": str(config), "PYTHONDONTWRITEBYTECODE": "1"}
            subprocess.run([sys.executable, str(install / "ynh/build.py"), str(upstream)], check=True, env=env)
            password = secrets.token_urlsafe(24)
            manage = [sys.executable, str(install / "ynh/manage.py")]
            subprocess.run([*manage, "install", "shelteradmin", "es"], input=password, text=True, check=True, env=env)

            def sql(statement):
                return subprocess.check_output([*cli, "asm3_smoke", "-e", statement], text=True).strip()

            assert sql("SELECT UserName FROM users WHERE DisableLogin=0") == "shelteradmin"
            assert sql("SELECT COUNT(*) FROM salesreceipt") == "0"
            assert sql("SELECT COUNT(*) FROM customreport") != "0", "Default reports missing"
            assert sql("SELECT ItemValue FROM configuration WHERE ItemName='Locale'") == "es"
            # Persistent marker represents data/media that must survive upgrade and restore.
            sql("INSERT INTO dbfs (ID, Path, Name, Content) VALUES (999999, '/', 'ynh-smoke-marker', 'c3Vydml2ZXM=')")
            # Exercise debug email logging and both 500 handlers with real
            # upstream modules. Delivery is stubbed; no email leaves the test.
            redaction_probe = r"""
import asm3.db, asm3.utils, asm3.al
import main
import web070 as web
marker = 'SECRET_BODY_AND_HEADER_SENTINEL'
asm3.al.LOG_DEBUG = True
sent = []
asm3.utils._send_email = lambda *a, **kw: sent.append(a) or True
asm3.utils.send_email(asm3.db.get_database(), 'root@example.test', 'staff@example.test', '', '', 'test', marker, 'plain', bulk=False)
assert sent
mail = []
asm3.utils.send_error_email = lambda *a: mail.append(a)
web.ctx.env = {'HTTP_COOKIE': marker, 'HTTP_X_ASM3_PROXY_SECRET': marker}
web.ctx.path = '/login'
web.ctx.query = '?password=' + marker
web.ctx.headers = []
assert marker not in str(main.asm_500_email().data)
assert marker not in repr(mail)
assert marker not in str(main.asm_500().data)
# Failure after native update_session must discard partially assembled privileges.
import sys, secrets, ynh_auth
password = sys.stdin.read()
main.session.update(main.session._initializer)
main.session.session_id = secrets.token_hex(20)
main.session.ip = '127.0.0.1'
web.ctx.ip = '127.0.0.1'
previous_id = main.session.session_id
ynh_auth.enabled = lambda: True
ynh_auth.is_managed = lambda *a: False
reached = []
def reject_after_session(*args):
    reached.append(True)
    raise ynh_auth.AccessDenied('forced_session_failure')
ynh_auth.mark_login = reject_after_session
post = asm3.utils.PostedData({'username':'shelteradmin','password':password}, 'es')
result = asm3.users.web_login(post, main.session, '127.0.0.1', 'test', main.PATH)
assert reached and result == 'FAIL'
assert main.session.get('user') is None and main.session.get('superuser') is None
assert main.session.session_id != previous_id
"""
            probe = subprocess.run([sys.executable, '-c', redaction_probe], cwd=upstream / 'src', env=env, input=password, capture_output=True, text=True)
            assert probe.returncode == 0, probe.stderr
            assert 'SECRET_BODY_AND_HEADER_SENTINEL' not in probe.stdout + probe.stderr
            for prefix in ("", "/refugio"):
                # Equivalent to the package's domain/path template regeneration.
                with config.open("a") as config_out:
                    config_out.write(f"base_url = https://asm3.example.test{prefix}\nservice_url = https://asm3.example.test{prefix}/service\n")
                web_port = free_port()
                web_log = work / "web.log"
                with web_log.open("w") as log:
                    web = subprocess.Popen([sys.executable, str(install / "ynh/server.py")], cwd=upstream / "src", env={**env, "ASM3_PORT": str(web_port), "ASM3_SCRIPT_NAME": prefix, "ASM3_INSTANCE": "asm3__2"}, stdout=log, stderr=log)

                def http_request(path, data=None, cookie=None):
                    conn = http.client.HTTPConnection("127.0.0.1", web_port, timeout=10)
                    headers = {"Host": "asm3.example.test", "X-Real-IP": "198.51.100.42"}
                    if cookie:
                        headers["Cookie"] = cookie
                    if data is not None:
                        headers["Content-Type"] = "application/x-www-form-urlencoded"
                    conn.request("POST" if data is not None else "GET", path, body=data, headers=headers)
                    response = conn.getresponse()
                    result = response.status, response.getheaders(), response.read()
                    conn.close()
                    return result

                wait_for(lambda: http_request("/login")[0] == 200, web, web_log)
                assert b"Acceso a Animal Shelter Manager" in http_request("/login")[2]
                status, headers, body = http_request("/")
                assert status in (301, 302, 303), (status, body[:200])
                location = dict(headers)["Location"]
                assert location.startswith("https://asm3.example.test"), location
                assert urllib.parse.urlparse(location).path.startswith(prefix + "/"), location
                status, headers, body = http_request("/login", urllib.parse.urlencode({"username": "shelteradmin", "password": password}))
                assert status == 200 and body == b"shelteradmin", (status, body[:300], web_log.read_text())
                cookies = [v for k, v in headers if k.lower() == "set-cookie"]
                assert cookies and any("asm_session_id_asm3__2=" in v for v in cookies), cookies
                assert all("secure" in v.lower() and f"path={prefix}/" in v.lower() for v in cookies), cookies
                status, _, body = http_request("/main", cookie="; ".join(v.split(";")[0] for v in cookies))
                assert status == 200 and b"controller" in body, (status, body[:200])
                assert http_request("/static/js/bundle/schema.js")[0] == 200
                marker = "PASSWORD_LOG_SENTINEL_" + secrets.token_hex(12)
                for endpoint in ("/login", "/mobile_login"):
                    if endpoint == "/login":
                        failed = http_request(endpoint, urllib.parse.urlencode({"username": "invalid_user", "password": marker}))
                        assert failed[2] == b"FAIL", failed[:1]
                    http_request(endpoint + "?b=" + marker)
                failed = http_request("/service", urllib.parse.urlencode({"method": "json_report", "username": "invalid_user", "password": marker}))
                assert b"Invalid username and password" in failed[2], failed[:1]
                http_request("/service?method=invalid&password=" + marker)
                assert marker not in web_log.read_text(), "Authentication leaked a password to logs"
                stop(web)
                web = None
            # Upgrade repairs legacy installs with no persisted Locale, without
            # overwriting a locale explicitly chosen in the application's UI.
            sql("DELETE FROM configuration WHERE ItemName='Locale'")
            subprocess.run([*manage, "upgrade"], check=True, env=env)
            assert sql("SELECT ItemValue FROM configuration WHERE ItemName='Locale'") == "es"
            assert sql("SELECT Content FROM dbfs WHERE Name='ynh-smoke-marker'") == "c3Vydml2ZXM="
            # Exercise the migration engine with a new update and a failed update.
            update_dir = upstream / "src/asm3/dbupdates"
            latest = max(int(p.stem) for p in update_dir.glob("*.py") if p.stem.isdigit())
            migration = update_dir / f"{latest + 1}.py"
            migration.write_text('dbo.execute("CREATE TABLE ynh_smoke_migration (ID INTEGER)")\n')
            subprocess.run([*manage, "upgrade"], check=True, env=env)
            assert sql("SELECT COUNT(*) FROM ynh_smoke_migration") == "0"
            failure = update_dir / f"{latest + 2}.py"
            failure.write_text('raise RuntimeError("intentional migration failure for smoke test")\n')
            rejected = subprocess.run([*manage, "upgrade"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert rejected.returncode != 0 and b"database migration failed" in rejected.stderr
            failure.unlink()
            dump = subprocess.check_output(["mariadb-dump", "--no-defaults", f"--socket={db_socket}", "-uroot", "--single-transaction", "asm3_smoke"])
            sql("DROP DATABASE asm3_smoke; CREATE DATABASE asm3_smoke;")
            subprocess.run([*cli, "asm3_smoke"], input=dump, check=True)
            subprocess.run([*manage, "upgrade"], check=True, env=env)
            assert sql("SELECT Content FROM dbfs WHERE Name='ynh-smoke-marker'") == "c3Vydml2ZXM="
            assert sql("SELECT UserName FROM users WHERE DisableLogin=0") == "shelteradmin"
            print("PASS: real MariaDB install, accounts, reports, root/subpath HTTP login, cookies, schema, upgrade and SQL/media restore")
        finally:
            stop(web)
            stop(db)


if __name__ == "__main__":
    main()
