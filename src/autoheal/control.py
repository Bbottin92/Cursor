 from __future__ import annotations
 
 import json
 import logging
 import os
 import socket
 import socketserver
 import threading
 from dataclasses import dataclass
 from pathlib import Path
 from typing import Any, Callable
 
 log = logging.getLogger("autoheal.control")
 
 
 class _ThreadingUnixStreamServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
     daemon_threads = True
 
 
 @dataclass(frozen=True)
 class ControlRequest:
     id: str | int | None
     method: str
     params: dict[str, Any]
     token: str | None
 
 
 @dataclass(frozen=True)
 class ControlResponse:
     id: str | int | None
     ok: bool
     result: Any = None
     error: str | None = None
 
 
 def start_control_server(
     socket_path: Path,
     *,
     handler: Callable[[ControlRequest], ControlResponse],
     stop_event: threading.Event,
 ) -> threading.Thread:
     socket_path.parent.mkdir(parents=True, exist_ok=True)
     try:
         if socket_path.exists():
             # Remove stale socket (best effort).
             socket_path.unlink()
     except Exception:
         pass
 
     class Handler(socketserver.StreamRequestHandler):
         def handle(self) -> None:
             while not stop_event.is_set():
                 line = self.rfile.readline()
                 if not line:
                     break
                 try:
                     req_raw = json.loads(line.decode("utf-8"))
                     req = ControlRequest(
                         id=req_raw.get("id"),
                         method=str(req_raw.get("method", "")),
                         params=dict(req_raw.get("params") or {}),
                         token=req_raw.get("token"),
                     )
                 except Exception:
                     resp = ControlResponse(id=None, ok=False, error="invalid request")
                     self.wfile.write((json.dumps(resp.__dict__) + "\n").encode("utf-8"))
                     continue
 
                 try:
                     resp = handler(req)
                 except Exception as e:
                     log.exception("control handler crashed: %s", e)
                     resp = ControlResponse(id=req.id, ok=False, error="handler error")
 
                 self.wfile.write((json.dumps(resp.__dict__) + "\n").encode("utf-8"))
 
     server = _ThreadingUnixStreamServer(str(socket_path), Handler)
     # Ensure we can notice stop_event without a client connecting.
     server.timeout = 0.5
 
     def _serve() -> None:
         with server:
             while not stop_event.is_set():
                 server.handle_request()
 
         try:
             server.server_close()
         except Exception:
             pass
 
         try:
             if socket_path.exists():
                 socket_path.unlink()
         except Exception:
             pass
 
     t = threading.Thread(target=_serve, name="autoheal-control", daemon=True)
     t.start()
     return t
 
 
 def call_control(
     socket_path: Path,
     *,
     method: str,
     params: dict[str, Any] | None = None,
     token: str | None = None,
     request_id: str | int | None = 1,
     timeout_seconds: int = 5,
 ) -> ControlResponse:
     req = {
         "id": request_id,
         "method": method,
         "params": params or {},
         "token": token,
     }
     data = (json.dumps(req) + "\n").encode("utf-8")
 
     try:
         with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
             s.settimeout(timeout_seconds)
             s.connect(str(socket_path))
             s.sendall(data)

             buf = b""
             while b"\n" not in buf:
                 chunk = s.recv(65536)
                 if not chunk:
                     break
                 buf += chunk
     except Exception as e:
         return ControlResponse(id=request_id, ok=False, error=str(e))
 
     if not buf:
         return ControlResponse(id=request_id, ok=False, error="no response")
 
     line = buf.split(b"\n", 1)[0]
     try:
         raw = json.loads(line.decode("utf-8"))
         return ControlResponse(
             id=raw.get("id"),
             ok=bool(raw.get("ok")),
             result=raw.get("result"),
             error=raw.get("error"),
         )
     except Exception:
         return ControlResponse(id=request_id, ok=False, error="invalid response")
