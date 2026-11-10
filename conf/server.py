"""Loopback-only WSGI host; Nginx removes the configured URL prefix."""
import hmac
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "upstream" / "src"))


class ProxyApplication:
    def __init__(self, application, prefix, instance="asm3", secret=""):
        self.secret = secret
        self.application = application
        self.prefix = prefix.rstrip("/")
        if not re.fullmatch(r"[a-z0-9_]+", instance):
            raise ValueError("Invalid instance id")
        self.cookies = {name: f"{name}_{instance}" for name in ("asm_session_id", "asm_remember_me")}

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") == "/_ynh_health":
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"ready"]
        if self.secret and not hmac.compare_digest(environ.get("HTTP_X_ASM3_PROXY_SECRET", "").encode("utf-8"), self.secret.encode("utf-8")):
            start_response("403 Forbidden", [("Content-Type", "text/plain")])
            return [b"Trusted proxy required"]
        environ["asm3.ynh_user"] = environ.get("HTTP_YNH_USER", "") if self.secret else ""
        # El servidor escucha en loopback y su único proxy previsto es Nginx local.
        environ["SCRIPT_NAME"] = self.prefix
        environ["wsgi.url_scheme"] = "https"
        environ["SERVER_PORT"] = "443"
        environ["REMOTE_ADDR"] = environ.get("HTTP_X_REAL_IP", environ["REMOTE_ADDR"])
        cookies = []
        for part in environ.get("HTTP_COOKIE", "").split(";"):
            name, sep, value = part.strip().partition("=")
            if not sep or name in self.cookies:
                continue
            for internal, external in self.cookies.items():
                if name == external:
                    name = internal
                    break
            cookies.append(f"{name}={value}")
        environ["HTTP_COOKIE"] = "; ".join(cookies)

        def respond(status, headers, exc_info=None):
            scoped = []
            for name, value in headers:
                if name.lower() == "set-cookie":
                    cookie_name, sep, rest = value.partition("=")
                    if cookie_name in self.cookies:
                        value = self.cookies[cookie_name] + sep + rest
                        if not re.search(r"(?i);\s*samesite=", value):
                            value += "; SameSite=Lax"
                        cookie_path = (self.prefix or "") + "/"
                        if re.search(r"(?i);\s*path=", value):
                            value = re.sub(r"(?i)(;\s*path=)[^;]*", lambda m: m[1] + cookie_path, value)
                        else:
                            value += "; Path=" + cookie_path
                scoped.append((name, value))
            return start_response(status, scoped, exc_info)

        return self.application(environ, respond)


if __name__ == "__main__":
    from cheroot.wsgi import Server
    import main
    import ynh_auth
    from asm3.sitedefs import get_string
    application = main.application
    if ynh_auth.enabled():
        main.app.add_processor(ynh_auth.processor(main.session, main.PATH))
        import ynh_mfa
        main.app.add_processor(ynh_mfa.processor(main.session, main.PATH))
    from web070.httpserver import StaticMiddleware

    if ynh_auth.enabled() and not get_string("ynh_proxy_secret"):
        raise RuntimeError("Missing trusted proxy secret")

    server = Server(
        ("127.0.0.1", int(os.environ["ASM3_PORT"])),
        ProxyApplication(StaticMiddleware(application), os.environ.get("ASM3_SCRIPT_NAME", ""), os.environ.get("ASM3_INSTANCE", "asm3"), get_string("ynh_proxy_secret", "")),
        numthreads=10,
    )
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
