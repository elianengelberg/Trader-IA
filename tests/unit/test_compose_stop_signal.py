"""Mission v3: a container's stop must reach the server process.

`docker stop` sends SIGTERM to the container's PID 1. With `sh -c "migrate && server"`, dash
(the image's /bin/sh) is PID 1 and the server its child: dash does not exec the last command of
an and-list, and as PID 1 it neither acts on nor forwards SIGTERM. The server never saw the stop;
after the grace period it was SIGKILLed with its writes, its stop record and its lease release
undone (reproduced with a PID namespace: reproduction/d3/pid1_sh.sh). The server must therefore
be ``exec``-ed. A static check: it cannot prove what Docker does, only that the file asks for it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = sorted(ROOT.glob("docker-compose*.yml"))


def _shell_wrapped_commands() -> list[tuple[str, str, str]]:
    out = []
    for path in COMPOSE:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, service in (doc.get("services") or {}).items():
            command = (service or {}).get("command")
            if (isinstance(command, list) and len(command) >= 3 and command[0] in ("sh", "/bin/sh", "bash")
                    and command[1] == "-c" and "tia.api.main" in str(command[2])):
                out.append((path.name, name, str(command[2])))
    return out


def test_the_production_server_command_is_found() -> None:
    assert any(where == "docker-compose.prod.yml" for where, _, _ in _shell_wrapped_commands()), (
        "the check would pass vacuously: no shell-wrapped server command in docker-compose.prod.yml")


@pytest.mark.parametrize("where,service,script", _shell_wrapped_commands())
def test_a_shell_wrapped_server_is_execed_so_it_receives_sigterm(where: str, service: str, script: str) -> None:
    last = script.split("&&")[-1].split(";")[-1].strip()
    assert last.startswith("exec "), f"{where}:{service}: the server must be exec'ed, got {last!r}"
