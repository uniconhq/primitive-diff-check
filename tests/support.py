"""What the tests share: the declaration, the sandbox flags and test inputs."""

import json
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
    """Write inputs.json and the files for a batch of (actual, expected) pairs."""
    batch = []
    for number, (item_id, (actual, expected)) in enumerate(pairs.items(), start=1):
        write(work / "in" / str(number) / "output", actual)
        write(work / "in" / f"t{number}" / f"{item_id}.ans", expected)
        batch.append(
            {
                "id": item_id,
                "inputs": {
                    "actual": {"file": f"in/{number}/output"},
                    "expected": {"file": f"in/t{number}/{item_id}.ans"},
                },
            }
        )
    document = {"schema_version": 4, "batch": batch}
    (work / "inputs.json").write_text(json.dumps(document))
