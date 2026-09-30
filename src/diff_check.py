#!/usr/local/bin/python3 -I
"""The diff-check primitive: compare an output with the expected one.

The harness mounts a working directory at `/work` (or the directory named by
the first argument) holding `inputs.json` and the files under `in/`. The
inputs are a batch: one item per test, each naming the `actual` output and
the `expected` one. For every item this program compares the two and reports
`accepted` with 1 point when they match and `wrong_answer` with 0 points when
they do not, then writes `outputs.json` with one entry per item in the same
order.

Two files match when they have the same lines once trailing whitespace is
removed from every line and trailing blank lines are removed from the end.
Leading whitespace and blank lines between other lines still count. The
files are compared as bytes, line by line, so neither is ever held in memory
whole and no text encoding is assumed.
"""

import json
import sys
from collections.abc import Iterable, Iterator
from itertools import zip_longest
from pathlib import Path

SCHEMA_VERSION = 3


class PrimitiveError(Exception):
    """The primitive could not do its work at all.

    The message is one sentence for a person and becomes `error` in
    `outputs.json`, which the harness turns into a `system_error` verdict.
    """


def main(argv: list[str]) -> int:
    """Compare every item `inputs.json` names and write `outputs.json`.

    Exits 0 whenever `outputs.json` was written, error or not; the harness
    reads the outcomes and any error from that file.
    """
    root = Path(argv[1]) if len(argv) > 1 else Path("/work")
    try:
        batch = [
            {"id": item_id, "outputs": check(actual, expected)}
            for item_id, actual, expected in read_inputs(root)
        ]
        document: dict[str, object] = {"schema_version": SCHEMA_VERSION, "batch": batch}
    except PrimitiveError as error:
        print(f"diff-check: {error}", file=sys.stderr)
        document = {"schema_version": SCHEMA_VERSION, "error": str(error)}
    write_json(root / "outputs.json", document)
    return 0


def read_inputs(root: Path) -> list[tuple[str, Path, Path]]:
    """Read `inputs.json` and return each item's id, actual file and expected file."""
    try:
        document = json.loads((root / "inputs.json").read_bytes())
    except FileNotFoundError:
        raise PrimitiveError("inputs.json is not in the working directory") from None
    except ValueError:
        raise PrimitiveError("inputs.json is not valid JSON") from None
    if not isinstance(document, dict):
        raise PrimitiveError("inputs.json is not a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise PrimitiveError(
            f"inputs.json is not written against contract version {SCHEMA_VERSION}"
        )
    batch = document.get("batch")
    if not isinstance(batch, list):
        raise PrimitiveError("inputs.json has no batch list")
    items = []
    for entry in batch:
        if not isinstance(entry, dict) or not isinstance(entry.get("inputs"), dict):
            raise PrimitiveError("a batch item has no inputs object")
        item_id = entry.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise PrimitiveError("a batch item has no id")
        inputs = entry["inputs"]
        actual = input_file(root, inputs, "actual", item_id)
        expected = input_file(root, inputs, "expected", item_id)
        items.append((item_id, actual, expected))
    return items


def input_file(root: Path, inputs: dict[str, object], name: str, item_id: str) -> Path:
    """Resolve a file input to a path, refusing anything outside `in/`."""
    value = inputs.get(name)
    if not isinstance(value, dict) or not isinstance(value.get("file"), str):
        raise PrimitiveError(f"the input named {name} of item {item_id} is not a file")
    path = (root / str(value["file"])).resolve()
    if not path.is_relative_to((root / "in").resolve()):
        raise PrimitiveError(f"the input named {name} of item {item_id} is outside in/")
    if not path.is_file():
        raise PrimitiveError(
            f"the input named {name} of item {item_id} is not in the working directory"
        )
    return path


def check(actual: Path, expected: Path) -> dict[str, object]:
    """Compare two files and return the outcome and the points."""
    if same(actual, expected):
        return {"outcome": "accepted", "points": 1}
    return {"outcome": "wrong_answer", "points": 0}


def same(actual: Path, expected: Path) -> bool:
    """Whether two files match, ignoring trailing whitespace and trailing blank lines.

    Once one file runs out of lines, every line left in the other must be
    blank, which is what ignoring trailing blank lines means.
    """
    with actual.open("rb") as left, expected.open("rb") as right:
        pairs = zip_longest(stripped(left), stripped(right), fillvalue=b"")
        return all(a == b for a, b in pairs)


def stripped(lines: Iterable[bytes]) -> Iterator[bytes]:
    """Yield each line without its trailing whitespace, line ending included."""
    for line in lines:
        yield line.rstrip()


def write_json(path: Path, document: dict[str, object]) -> None:
    """Write a JSON file whole: to a temporary name first, then renamed."""
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    partial.replace(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
