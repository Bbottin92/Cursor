 from __future__ import annotations
 
 import logging
 import logging.handlers
 from pathlib import Path
 
 
 def setup_logging(log_path: Path, verbose: bool = False) -> None:
     log_path.parent.mkdir(parents=True, exist_ok=True)
 
     level = logging.DEBUG if verbose else logging.INFO
 
     root = logging.getLogger()
     root.setLevel(level)
 
     fmt = logging.Formatter(
         fmt="%(asctime)sZ %(levelname)s %(name)s %(message)s",
         datefmt="%Y-%m-%dT%H:%M:%S",
     )
 
     # File log with rotation
     file_handler = logging.handlers.RotatingFileHandler(
         log_path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
     )
     file_handler.setLevel(level)
     file_handler.setFormatter(fmt)
 
     # Stderr log for foreground runs
     stream_handler = logging.StreamHandler()
     stream_handler.setLevel(level)
     stream_handler.setFormatter(fmt)
 
     # Avoid duplicating handlers on repeated setup calls.
     if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
         root.addHandler(file_handler)
     if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
         root.addHandler(stream_handler)
