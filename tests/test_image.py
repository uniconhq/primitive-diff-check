"""The image, run on Docker under the harness's sandbox flags."""

import json
from pathlib import Path
from typing import Any

import pytest

from support import Check, RunImage, batch_inputs

pytestmark = pytest.mark.image


def test_a_batch_is_compared_inside_the_sandbox(
    tmp_path: Path, run_image: RunImage, check: Check
) -> None:
    """Matching pairs are accepted with a point, a differing pair is a wrong answer."""
    batch_inputs(
        tmp_path,
        {
            "1": (b"1 2 3\n", b"1 2 3\n"),
            "2": (b"1 2 3  \r\n\r\n", b"1 2 3\n"),
            "3": (b"1 2 3\n", b"1 2 4\n"),
        },
    )
    check(json.loads((tmp_path / "inputs.json").read_text()), "inputs_file")
    result = run_image(tmp_path)
    check(result, "outputs_file")
    assert [(entry["id"], entry["outputs"]) for entry in result["batch"]] == [
        ("1", {"outcome": "accepted", "points": 1}),
        ("2", {"outcome": "accepted", "points": 1}),
        ("3", {"outcome": "wrong_answer", "points": 0}),
    ]


def test_a_missing_file_is_an_error_inside_the_sandbox(
    tmp_path: Path, run_image: RunImage, check: Check
) -> None:
    """A file inputs.json names but the directory lacks is an error, not a grade."""
    document: dict[str, Any] = {
        "schema_version": 4,
        "batch": [
            {
                "id": "1",
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
        == "the input named actual of item 1 is not in the working directory"
    )
