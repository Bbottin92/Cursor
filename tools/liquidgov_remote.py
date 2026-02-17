#!/usr/bin/env python3
"""
One-shot remote editor for LiquidGov.US (cPanel + File Manager API).

Why this exists:
  - No SSH on many shared hosting plans.
  - cPanel still exposes a JSON API that can read/write text files.
  - This script lets you do common edits in ONE command (get/put/replace),
    instead of clicking through File Manager or writing ad-hoc snippets.

It talks to cPanel UAPI endpoints over HTTPS using HTTP Basic auth:
  https://HOST:2083/execute/Fileman/get_file_content
  https://HOST:2083/execute/Fileman/save_file_content
  https://HOST:2083/execute/Fileman/list_files

Required env vars (recommended):
  CPANEL_HOST   e.g. host04.nunames.net
  CPANEL_USER   e.g. liquidgo
  CPANEL_PASS   your cPanel password

Optional env vars:
  CPANEL_PORT=2083
  LIQUIDGOV_REMOTE_ROOT=/home/<user>/public_html   (default)
  CPANEL_INSECURE=1  (DISABLES TLS verification; not recommended)
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import os
import posixpath
import ssl
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request


class CPanelError(RuntimeError):
    pass


def _now_stamp() -> str:
    # Example: 20260217T061234Z
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _b64_basic_auth(user: str, password: str) -> str:
    raw = f"{user}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _ssl_context(insecure: bool) -> ssl.SSLContext:
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


def _http_json(
    *,
    url: str,
    method: str,
    headers: dict[str, str],
    data: bytes | None,
    ctx: ssl.SSLContext,
    timeout_s: int = 30,
) -> dict:
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout_s) as resp:
            body = resp.read()
            try:
                return json.loads(body.decode("utf-8", errors="replace"))
            except Exception as e:  # noqa: BLE001
                snippet = body[:300].decode("utf-8", errors="replace")
                raise CPanelError(f"Non-JSON response from cPanel: {snippet}") from e
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        snippet = raw[:300].decode("utf-8", errors="replace")
        raise CPanelError(f"HTTP {e.code} from cPanel: {snippet}") from e


class CPanelClient:
    def __init__(
        self,
        *,
        host: str,
        user: str,
        password: str,
        port: int = 2083,
        insecure_tls: bool = False,
    ) -> None:
        self.host = host
        self.user = user
        self._password = password
        self.port = port
        self.ctx = _ssl_context(insecure_tls)

    @property
    def base_url(self) -> str:
        return f"https://{self.host}:{self.port}"

    def execute(self, module: str, function: str, params: dict[str, str], *, method: str = "GET") -> dict:
        method = method.upper()
        if method not in ("GET", "POST"):
            raise ValueError("method must be GET or POST")

        path = f"/execute/{module}/{function}"
        url = self.base_url + path

        headers = {
            "Authorization": _b64_basic_auth(self.user, self._password),
            "User-Agent": "liquidgov_remote.py/1.0",
            "Accept": "application/json",
        }

        if method == "GET":
            if params:
                url += "?" + urllib.parse.urlencode(params)
            return _http_json(url=url, method="GET", headers=headers, data=None, ctx=self.ctx)

        body = urllib.parse.urlencode(params).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return _http_json(url=url, method="POST", headers=headers, data=body, ctx=self.ctx)

    def _ensure_ok(self, resp: dict, what: str) -> dict:
        if resp.get("status") != 1:
            errors = resp.get("errors") or []
            msg = errors[0] if errors else "Unknown cPanel error"
            raise CPanelError(f"{what} failed: {msg}")
        return resp

    def list_dir(self, dir_path: str) -> list[dict]:
        resp = self.execute("Fileman", "list_files", {"dir": dir_path, "showdotfiles": "1"}, method="GET")
        self._ensure_ok(resp, f"list_dir({dir_path})")
        return resp.get("data") or []

    def read_text_file(self, abs_path: str) -> str:
        d, f = split_dir_file(abs_path)
        resp = self.execute("Fileman", "get_file_content", {"dir": d, "file": f}, method="GET")
        self._ensure_ok(resp, f"read_file({abs_path})")
        data = resp.get("data") or {}
        return data.get("content") or ""

    def write_text_file(self, abs_path: str, content: str) -> None:
        d, f = split_dir_file(abs_path)
        resp = self.execute("Fileman", "save_file_content", {"dir": d, "file": f, "content": content}, method="POST")
        self._ensure_ok(resp, f"write_file({abs_path})")

    def backup_file(self, abs_path: str) -> str:
        content = self.read_text_file(abs_path)
        d, f = split_dir_file(abs_path)
        backup_name = f"{f}.bak.{_now_stamp()}"
        backup_path = posixpath.join(d, backup_name)
        self.write_text_file(backup_path, content)
        return backup_path


def split_dir_file(abs_path: str) -> tuple[str, str]:
    p = abs_path.rstrip("/")
    d = posixpath.dirname(p) or "/"
    f = posixpath.basename(p)
    if not f:
        raise ValueError(f"Not a file path: {abs_path}")
    return d, f


def remote_root(user: str) -> str:
    rr = os.environ.get("LIQUIDGOV_REMOTE_ROOT", "").strip()
    if rr:
        return rr.rstrip("/")
    return f"/home/{user}/public_html"


def to_abs_remote_path(user: str, path: str) -> str:
    path = path.strip()
    if not path:
        raise ValueError("Empty remote path")
    if path.startswith("/"):
        return posixpath.normpath(path)
    return posixpath.normpath(posixpath.join(remote_root(user), path))


def _cmd_doctor(cp: CPanelClient) -> int:
    rr = remote_root(cp.user)
    print(f"cPanel: {cp.base_url}")
    print(f"user:  {cp.user}")
    print(f"root:  {rr}")
    print("")
    try:
        entries = cp.list_dir(rr)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: cannot list {rr}: {e}")
        return 2

    files = [e.get("file") for e in entries]
    print(f"{rr} contains {len(files)} entries.")
    for name in sorted(files)[:30]:
        print(" -", name)
    return 0


def _cmd_ls(cp: CPanelClient, path: str | None) -> int:
    rr = to_abs_remote_path(cp.user, path) if path else remote_root(cp.user)
    entries = cp.list_dir(rr)
    for e in entries:
        name = e.get("file", "?")
        typ = e.get("type", "?")
        size = e.get("humansize") or e.get("size") or ""
        print(f"{typ:6} {size:>8} {name}")
    return 0


def _cmd_get(cp: CPanelClient, remote: str, out_path: str | None) -> int:
    abs_remote = to_abs_remote_path(cp.user, remote)
    content = cp.read_text_file(abs_remote)
    if not out_path or out_path == "-":
        sys.stdout.write(content)
        if not content.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Wrote {len(content)} bytes -> {out_path}")
    return 0


def _cmd_put(cp: CPanelClient, local_path: str, remote: str | None, *, backup: bool) -> int:
    with open(local_path, "r", encoding="utf-8") as f:
        content = f.read()

    if remote:
        abs_remote = to_abs_remote_path(cp.user, remote)
    else:
        abs_remote = posixpath.join(remote_root(cp.user), posixpath.basename(local_path))

    if backup:
        try:
            bak = cp.backup_file(abs_remote)
            print(f"Backup: {bak}")
        except CPanelError:
            # If file didn't exist yet, backup isn't possible/needed.
            pass

    cp.write_text_file(abs_remote, content)
    print(f"Updated: {abs_remote}  ({len(content)} bytes)")
    return 0


def _cmd_replace(
    cp: CPanelClient,
    remote: str,
    old: str,
    new: str,
    *,
    count: int | None,
    backup: bool,
) -> int:
    abs_remote = to_abs_remote_path(cp.user, remote)
    content = cp.read_text_file(abs_remote)
    if old not in content:
        raise CPanelError("Old string not found; refusing to write unchanged file.")

    if backup:
        bak = cp.backup_file(abs_remote)
        print(f"Backup: {bak}")

    if count is None:
        updated = content.replace(old, new)
    else:
        updated = content.replace(old, new, count)

    cp.write_text_file(abs_remote, updated)
    n = content.count(old) if count is None else min(content.count(old), count)
    print(f"Replaced {n} occurrence(s) in: {abs_remote}")
    return 0


def _cmd_tail(cp: CPanelClient, remote_log: str, lines: int) -> int:
    abs_remote = to_abs_remote_path(cp.user, remote_log)
    content = cp.read_text_file(abs_remote)
    out = content.splitlines()[-lines:]
    for ln in out:
        print(ln)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="liquidgov_remote.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="One-shot remote editor for LiquidGov via cPanel API.",
        epilog=textwrap.dedent(
            """\
            Examples:
              # List webroot
              python3 tools/liquidgov_remote.py ls

              # Download styles.css
              python3 tools/liquidgov_remote.py get styles.css --out styles.css

              # Upload a local file to webroot (auto-remote path)
              python3 tools/liquidgov_remote.py put styles.css

              # Replace a string in a remote file
              python3 tools/liquidgov_remote.py replace styles.css --old "flex-wrap: wrap;" --new "flex-wrap: nowrap;"
            """
        ),
    )

    p.add_argument("--host", default=os.environ.get("CPANEL_HOST", ""), help="cPanel host (or env CPANEL_HOST)")
    p.add_argument("--port", type=int, default=int(os.environ.get("CPANEL_PORT", "2083") or "2083"))
    p.add_argument("--user", default=os.environ.get("CPANEL_USER", ""), help="cPanel username (or env CPANEL_USER)")
    p.add_argument(
        "--insecure",
        action="store_true",
        default=os.environ.get("CPANEL_INSECURE", "") in ("1", "true", "TRUE", "yes", "YES"),
        help="Disable TLS verification (not recommended)",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Check connectivity and list webroot")

    sp = sub.add_parser("ls", help="List a remote directory (default: webroot)")
    sp.add_argument("path", nargs="?", help="Remote dir path (absolute or relative to webroot)")

    sp = sub.add_parser("get", help="Download/print a remote text file")
    sp.add_argument("remote", help="Remote file path (absolute or relative to webroot)")
    sp.add_argument("--out", help="Write to local file (default: stdout)")

    sp = sub.add_parser("put", help="Upload a local text file")
    sp.add_argument("local", help="Local file path")
    sp.add_argument("remote", nargs="?", help="Remote file path (default: webroot/<basename>)")
    sp.add_argument("--no-backup", action="store_true", help="Do not create remote .bak backup")

    sp = sub.add_parser("replace", help="Replace text in a remote file")
    sp.add_argument("remote", help="Remote file path")
    sp.add_argument("--old", required=True, help="Old string (must exist)")
    sp.add_argument("--new", required=True, help="New string")
    sp.add_argument("--count", type=int, help="Replace at most N occurrences")
    sp.add_argument("--no-backup", action="store_true", help="Do not create remote .bak backup")

    default_user = os.environ.get("CPANEL_USER") or "<user>"
    default_log = f"/home/{default_user}/logs/liquidgov_us.php.error.log"
    sp = sub.add_parser("tail", help="Tail a remote log file (text)")
    sp.add_argument("remote_log", nargs="?", default=default_log, help="Remote log path")
    sp.add_argument("--lines", type=int, default=120, help="Number of lines")

    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    password = os.environ.get("CPANEL_PASS", "")
    if not args.host or not args.user or not password:
        raise CPanelError(
            "Missing credentials. Set env vars: CPANEL_HOST, CPANEL_USER, CPANEL_PASS (optionally CPANEL_PORT)."
        )

    cp = CPanelClient(
        host=args.host,
        port=args.port,
        user=args.user,
        password=password,
        insecure_tls=args.insecure,
    )

    if args.cmd == "doctor":
        return _cmd_doctor(cp)
    if args.cmd == "ls":
        return _cmd_ls(cp, args.path)
    if args.cmd == "get":
        return _cmd_get(cp, args.remote, args.out)
    if args.cmd == "put":
        return _cmd_put(cp, args.local, args.remote, backup=not args.no_backup)
    if args.cmd == "replace":
        return _cmd_replace(cp, args.remote, args.old, args.new, count=args.count, backup=not args.no_backup)
    if args.cmd == "tail":
        return _cmd_tail(cp, args.remote_log, args.lines)

    raise CPanelError(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except CPanelError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)

