from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CmdResult:
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def run(
    argv: list[str],
    *,
    timeout_seconds: int = 30,
) -> CmdResult:
    p = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
    )
    return CmdResult(argv=argv, exit_code=int(p.returncode), stdout=p.stdout, stderr=p.stderr)
