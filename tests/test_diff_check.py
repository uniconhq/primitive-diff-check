"""The comparison and the inputs.json and outputs.json handling, run in-process."""

import json
import time
from collections.abc import Callable
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


def test_millions_of_trailing_blank_lines_are_judged_at_once(tmp_path: Path) -> None:
    """A right answer followed by a flood of empty lines is accepted quickly."""
    left = write(tmp_path / "actual", b"42\n" + b"\n" * 8_000_000)
    right = write(tmp_path / "expected", b"42\n")
    started = time.monotonic()

    assert diff_check.same(left, right)
    assert diff_check.same(right, left)
    assert time.monotonic() - started < 2


LARGE = 32 * 1024 * 1024
"""The most a sandbox-run output holds."""


@pytest.mark.parametrize(
    ("actual", "expected", "matches"),
    [
        (lambda: b"1\n" * (LARGE // 2), lambda: b"1\n" * (LARGE // 2), True),
        (lambda: b"\n" * LARGE, lambda: b"\n" * (LARGE - 2) + b"x\n", False),
        (lambda: b"1\r\n" * (LARGE // 3), lambda: b"1\n" * (LARGE // 3), True),
        (lambda: b"1 \n" * (LARGE // 3), lambda: b"1\n" * (LARGE // 3), True),
        (
            lambda: b"1" + b" " * LARGE + b"2",
            lambda: b"1" + b"\t" * LARGE + b"2",
            False,
        ),
        (lambda: b"1" + b" " * LARGE + b"\n2\n", lambda: b"1\n2", True),
        (lambda: b"x" * LARGE, lambda: b"x" * LARGE + b"\n", True),
    ],
)
def test_the_largest_outputs_are_compared_in_a_moment(
    tmp_path: Path,
    actual: Callable[[], bytes],
    expected: Callable[[], bytes],
    matches: bool,
) -> None:
    """An output as large as sandbox-run keeps, with millions of lines, one
    line or every line ending in whitespace, is compared with no step per
    line: in a few seconds at most even on a slow machine."""
    left = write(tmp_path / "actual", actual())
    right = write(tmp_path / "expected", expected())
    for one, two in ((left, right), (right, left)):
        started = time.monotonic()
        assert diff_check.same(one, two) is matches
        assert time.monotonic() - started < 5


@pytest.mark.parametrize(
    ("actual", "expected", "matches"),
    [
        (b"ab  ", b"ab\n", True),
        (b"ab  \t\n\n", b"ab", True),
        (b"ab  c", b"ab c", False),
        (b"ab  c", b"ab  c  \n", True),
        (b"  \n  ab", b"\nab", False),
        (b"  \n  ab", b"\n  ab", True),
        (b"1 2 \n3", b"1 2\n3", True),
        (b"1 2 \n3", b"1 23", False),
        (b"xy \t\r\x0b\x0c \nz\n", b"xy\nz", True),
    ],
)
def test_whitespace_across_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    actual: bytes,
    expected: bytes,
    matches: bool,
) -> None:
    """Whitespace split over the blocks the files are read in is judged as if
    read whole."""
    monkeypatch.setattr(diff_check, "BLOCK", 2)
    left = write(tmp_path / "actual", actual)
    right = write(tmp_path / "expected", expected)
    assert diff_check.same(left, right) is matches
    assert diff_check.same(right, left) is matches


@pytest.mark.parametrize(
    ("data", "lines"),
    [
        (b"a\r\nb \n c\t\n", b"a\nb\n c\n"),
        (b"a \r\n\x0c\n", b"a\n\n"),
        (b"a \t\r\x0b\x0c \t\nb  c   \n", b"a\nb  c\n"),
        (b"a b", b"a b"),
    ],
)
def test_trim_lines(data: bytes, lines: bytes) -> None:
    """Every line loses its trailing whitespace, however long the run."""
    assert diff_check.trim_lines(data) == lines


def outputs(work: Path) -> dict[str, Any]:
    """Run the program over a working directory and read outputs.json."""
    assert diff_check.main(["diff-check", str(work)]) == 0
    document: dict[str, Any] = json.loads(
        (work / "outputs.json").read_text(encoding="utf-8")
    )
    return document


def test_a_batch_gets_one_entry_per_item_in_order(tmp_path: Path) -> None:
    """Each item gets its outcome alone, under its own test and in its place."""
    batch_inputs(
        tmp_path,
        {
            "main/2": (b"4\n", b"4\n"),
            "main/10": (b"5\n", b"6\n"),
            "samples/1": (b"x \n\n", b"x\n"),
        },
    )
    assert outputs(tmp_path) == {
        "schema_version": 5,
        "batch": [
            {"test": "main/2", "outputs": {"outcome": "accepted"}},
            {"test": "main/10", "outputs": {"outcome": "wrong_answer"}},
            {"test": "samples/1", "outputs": {"outcome": "accepted"}},
        ],
    }


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (None, "inputs.json is not in the working directory"),
        ("[1", "inputs.json is not valid JSON"),
        ([], "inputs.json is not a JSON object"),
        ({"schema_version": 4, "batch": []}, "contract version 5"),
        ({"schema_version": 5, "inputs": {}}, "no batch list"),
        ({"schema_version": 5, "batch": [{"test": "main/1"}]}, "no inputs"),
        (
            {"schema_version": 5, "batch": [{"id": "main/1", "inputs": {}}]},
            "has no test",
        ),
        (
            {
                "schema_version": 5,
                "batch": [{"test": "main/1", "inputs": {}}],
            },
            "actual of test main/1 is not a file",
        ),
        (
            {
                "schema_version": 5,
                "batch": [
                    {
                        "test": "main/1",
                        "inputs": {
                            "actual": {"file": "in/../inputs.json"},
                            "expected": {"file": "in/a"},
                        },
                    }
                ],
            },
            "actual of test main/1 is outside in/",
        ),
        (
            {
                "schema_version": 5,
                "batch": [
                    {
                        "test": "main/1",
                        "inputs": {
                            "actual": {"file": "in/missing"},
                            "expected": {"file": "in/a"},
                        },
                    }
                ],
            },
            "actual of test main/1 is not in the working directory",
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
