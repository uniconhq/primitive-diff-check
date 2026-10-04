"""The comparison and the inputs.json and outputs.json handling, run in-process."""

import json
from pathlib import Path
from typing import Any

import pytest

import diff_check
from support import batch_inputs, write


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        (b"1 2 3\n", b"1 2 3\n"),
        (b"1 2 3", b"1 2 3\n"),
        (b"1 2 3   \t\n", b"1 2 3\n"),
        (b"1 2 3\r\n4\r\n", b"1 2 3\n4\n"),
        (b"yes\n\n\n", b"yes\n"),
        (b"yes\n", b"yes\n\n  \n"),
        (b"", b"\n\n"),
        (b"", b""),
    ],
)
def test_matching_files_are_the_same(
    tmp_path: Path, actual: bytes, expected: bytes
) -> None:
    """Trailing whitespace on a line and trailing blank lines do not count."""
    left = write(tmp_path / "actual", actual)
    right = write(tmp_path / "expected", expected)
    assert diff_check.same(left, right)
    assert diff_check.same(right, left)


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        (b"1 2 3\n", b"1 2 4\n"),
        (b" 1 2 3\n", b"1 2 3\n"),
        (b"1  2 3\n", b"1 2 3\n"),
        (b"a\n\nb\n", b"a\nb\n"),
        (b"a\n", b"a\nb\n"),
        (b"", b"0\n"),
        (b"\n\nyes\n", b"yes\n"),
    ],
)
def test_differing_files_are_not_the_same(
    tmp_path: Path, actual: bytes, expected: bytes
) -> None:
    """Leading whitespace, inner spacing, inner blank lines and content all count."""
    left = write(tmp_path / "actual", actual)
    right = write(tmp_path / "expected", expected)
    assert not diff_check.same(left, right)
    assert not diff_check.same(right, left)


def outputs(work: Path) -> dict[str, Any]:
    """Run the program over a working directory and read outputs.json."""
    assert diff_check.main(["diff-check", str(work)]) == 0
    document: dict[str, Any] = json.loads(
        (work / "outputs.json").read_text(encoding="utf-8")
    )
    return document


def test_a_batch_gets_one_entry_per_item_in_order(tmp_path: Path) -> None:
    """Each item gets its outcome and points, under its own id and in its place."""
    batch_inputs(
        tmp_path,
        {"2": (b"4\n", b"4\n"), "10": (b"5\n", b"6\n"), "1": (b"x \n\n", b"x\n")},
    )
    assert outputs(tmp_path) == {
        "schema_version": 4,
        "batch": [
            {"id": "2", "outputs": {"outcome": "accepted", "points": 1}},
            {"id": "10", "outputs": {"outcome": "wrong_answer", "points": 0}},
            {"id": "1", "outputs": {"outcome": "accepted", "points": 1}},
        ],
    }


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (None, "inputs.json is not in the working directory"),
        ("[1", "inputs.json is not valid JSON"),
        ([], "inputs.json is not a JSON object"),
        ({"schema_version": 2, "batch": []}, "contract version 4"),
        ({"schema_version": 4, "inputs": {}}, "no batch list"),
        ({"schema_version": 4, "batch": [{"id": "1"}]}, "no inputs"),
        (
            {"schema_version": 4, "batch": [{"id": "", "inputs": {}}]},
            "has no id",
        ),
        (
            {
                "schema_version": 4,
                "batch": [{"id": "1", "inputs": {}}],
            },
            "actual of item 1 is not a file",
        ),
        (
            {
                "schema_version": 4,
                "batch": [
                    {
                        "id": "1",
                        "inputs": {
                            "actual": {"file": "in/../inputs.json"},
                            "expected": {"file": "in/a"},
                        },
                    }
                ],
            },
            "actual of item 1 is outside in/",
        ),
        (
            {
                "schema_version": 4,
                "batch": [
                    {
                        "id": "1",
                        "inputs": {
                            "actual": {"file": "in/missing"},
                            "expected": {"file": "in/a"},
                        },
                    }
                ],
            },
            "actual of item 1 is not in the working directory",
        ),
    ],
)
def test_inputs_it_cannot_use_are_an_error(
    tmp_path: Path, document: object, message: str
) -> None:
    """Anything that stops the primitive working is `error` alone, in one sentence."""
    if isinstance(document, str):
        (tmp_path / "inputs.json").write_text(document)
    elif document is not None:
        (tmp_path / "inputs.json").write_text(json.dumps(document))
    result = outputs(tmp_path)
    assert set(result) == {"schema_version", "error"}
    assert message in result["error"]
