"""The image, run on Docker under the harness's sandbox flags."""

import json
from pathlib import Path
from typing import Any

import pytest

from support import Check, RunImage, batch_inputs, declaration

pytestmark = pytest.mark.image


def test_a_batch_is_compared_inside_the_sandbox(
    tmp_path: Path, run_image: RunImage, check: Check
) -> None:
    """Matching pairs are accepted, a differing pair is a wrong answer."""
    batch_inputs(
        tmp_path,
        {
            "samples/1": (b"1 2 3\n", b"1 2 3\n"),
            "main/1": (b"1 2 3  \r\n\r\n", b"1 2 3\n"),
            "main/2": (b"1 2 3\n", b"1 2 4\n"),
        },
    )
    check(json.loads((tmp_path / "inputs.json").read_text()), "inputs_file")
    result = run_image(tmp_path)
    check(result, "outputs_file")
    assert [(entry["test"], entry["outputs"]) for entry in result["batch"]] == [
        ("samples/1", {"outcome": "accepted"}),
        ("main/1", {"outcome": "accepted"}),
        ("main/2", {"outcome": "wrong_answer"}),
    ]


def test_the_largest_outputs_fit_the_limits_inside_the_sandbox(
    tmp_path: Path, run_image: RunImage
) -> None:
    """Outputs as large as sandbox-run keeps, every line ending in whitespace,
    are compared under the container's memory and its CPU time summed over
    the batch, which the kernel holds as `RLIMIT_CPU`."""
    size = 32 * 1024 * 1024
    batch_inputs(
        tmp_path,
        {
            "main/1": (b"1\r\n" * (size // 3), b"1\n" * (size // 3)),
            "main/2": (b"1 \n" * (size // 3), b"1\n" * (size // 3 - 1) + b"2\n"),
        },
    )
    limits = dict(declaration()["limits"])
    limits["time_ms"] *= 2
    limits["cpu_ms"] *= 2
    result = run_image(tmp_path, limits)
    assert [(entry["test"], entry["outputs"]) for entry in result["batch"]] == [
        ("main/1", {"outcome": "accepted"}),
        ("main/2", {"outcome": "wrong_answer"}),
    ]


def test_a_missing_file_is_an_error_inside_the_sandbox(
    tmp_path: Path, run_image: RunImage, check: Check
) -> None:
    """A file inputs.json names but the directory lacks is an error, not a grade."""
    document: dict[str, Any] = {
        "schema_version": 5,
        "batch": [
            {
                "test": "main/1",
                "inputs": {"actual": {"file": "in/1"}, "expected": {"file": "in/2"}},
            }
        ],
    }
    (tmp_path / "in").mkdir()
    (tmp_path / "inputs.json").write_text(json.dumps(document))
    result = run_image(tmp_path)
    check(result, "outputs_file")
    assert (
        result["error"]
        == "the input named actual of test main/1 is not in the working directory"
    )
