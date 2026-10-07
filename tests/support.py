"""What the tests share: the declaration, the sandbox flags and test inputs."""

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
NAME = "primitive-diff-check"
SIBLING_SCHEMA = ROOT.parent / "runner" / "schemas" / "primitive.schema.json"

RunImage = Callable[..., dict[str, Any]]
Check = Callable[[dict[str, Any], str], None]


def declaration() -> dict[str, Any]:
    """This repo's primitive.yaml."""
    document: dict[str, Any] = yaml.safe_load((ROOT / "primitive.yaml").read_text())
    return document


def sandbox_flags(limits: dict[str, int]) -> list[str]:
    """The docker run flags the harness gives a step container."""
    memory = f"{limits['memory_mb']}m"
    cpu_seconds = math.ceil(limits["cpu_ms"] / 1000)
    file_bytes = limits["output_mb"] * 1024 * 1024
    return [
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--security-opt=seccomp=builtin",
        "--user=65532:65532",
        f"--memory={memory}",
        f"--memory-swap={memory}",
        f"--pids-limit={limits['pids']}",
        f"--ulimit=cpu={cpu_seconds}:{cpu_seconds}",
        f"--ulimit=fsize={file_bytes}:{file_bytes}",
        "--cpus=1",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m",
    ]


def open_up(work: Path) -> None:
    """Let user 65532 in the container write the working directory and read `in/`."""
    for path in [work, *work.rglob("*")]:
        path.chmod(0o777 if path.is_dir() else 0o666)


def write(path: Path, data: bytes) -> Path:
    """Write a file, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def batch_inputs(work: Path, pairs: dict[str, tuple[bytes, bytes]]) -> None:
    """Write inputs.json and the files for a batch of (actual, expected) pairs.

    The pairs are keyed by test id, `<group>/<test>`. The files sit under
    numbered folders, as the harness places them, since an id is no file name.
    """
    batch = []
    for number, (test, (actual, expected)) in enumerate(pairs.items()):
        write(work / "in" / str(2 * number + 1) / "output", actual)
        write(work / "in" / str(2 * number + 2) / "answer", expected)
        batch.append(
            {
                "test": test,
                "inputs": {
                    "actual": {"file": f"in/{2 * number + 1}/output"},
                    "expected": {"file": f"in/{2 * number + 2}/answer"},
                },
            }
        )
    document = {"schema_version": 5, "batch": batch}
    (work / "inputs.json").write_text(json.dumps(document))
