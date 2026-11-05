#!/usr/bin/env python3
"""Create the stable update PR on the configured Forgejo instance, idempotently."""
import json
import os
import re
import urllib.request

BRANCH = "automation/asm3-stable"


def propose(server, repository, token):
    if not server.startswith(("https://", "http://")):
        raise ValueError("FORGEJO_SERVER_URL must be an HTTP(S) URL")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("FORGEJO_REPOSITORY must be owner/repository")
    if not token:
        raise ValueError("ASM3_UPDATE_TOKEN is required to create update pull requests")
    base = server.rstrip("/") + "/api/v1/repos/" + repository

    def api(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=data, headers={
            "Authorization": "token " + token,
            "Accept": "application/json", "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)

    page = 1
    while True:
        pulls = api(f"/pulls?state=open&limit=50&page={page}")
        for pull in pulls:
            if pull["head"]["ref"] == BRANCH and pull["head"].get("repo", {}).get("full_name") == repository:
                print(pull["html_url"])
                return pull
        if len(pulls) < 50:
            break
        page += 1
    repo = api("")
    pull = api("/pulls", {
        "head": BRANCH, "base": repo["default_branch"],
        "title": "Update ASM3 to latest stable",
        "body": "Updates the pinned official ASM3 release, source commit, SHA-256 and package version.\n\nPackage validation and the real MariaDB lifecycle smoke test passed before this proposal. Full YunoHost package_check is available separately on a prepared runner.",
    })
    print(pull["html_url"])
    return pull


if __name__ == "__main__":
    propose(os.environ["FORGEJO_SERVER_URL"], os.environ["FORGEJO_REPOSITORY"], os.environ.get("FORGEJO_TOKEN", ""))
