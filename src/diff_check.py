#!/usr/local/bin/python3 -I
"""The diff-check primitive: compare an output with the expected one.

The harness mounts a working directory at `/work` (or the directory named by
the first argument) holding `inputs.json` and the files under `in/`. The
inputs are a batch: one item per test, keyed by the test's id, each naming
the `actual` output and the `expected` one. For every item this program
compares the two and reports the outcome `accepted` when they match and
`wrong_answer` when they do not, then writes `outputs.json` with one entry per
item, under the same test and in the same order. It reads both files as data
and writes no other file.

Two files match when they have the same lines once trailing whitespace is
removed from every line and trailing blank lines are removed from the end.
Leading whitespace and blank lines between other lines still count. The
files are compared as bytes, in blocks, so no text encoding is assumed and
the time is linear in their size.
"""

import json
import sys
from collections.abc import Iterator
from itertools import chain
from pathlib import Path
from typing import BinaryIO

SCHEMA_VERSION = 5
BLOCK = 1 << 20
LINE_SPACE = b" \t\r\x0b\x0c"
"""The whitespace `bytes.rstrip` takes off the end of a line, but the newline."""
LINE_ENDS = tuple(bytes((space,)) + b"\n" for space in LINE_SPACE)
TRIM_PASSES = 4


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
            {"test": test, "outputs": check(actual, expected)}
            for test, actual, expected in read_inputs(root)
        ]
        document: dict[str, object] = {"schema_version": SCHEMA_VERSION, "batch": batch}
    except PrimitiveError as error:
        print(f"diff-check: {error}", file=sys.stderr)
        document = {"schema_version": SCHEMA_VERSION, "error": str(error)}
    write_json(root / "outputs.json", document)
    return 0


def read_inputs(root: Path) -> list[tuple[str, Path, Path]]:
    """Read `inputs.json` and return each item's test, actual file and expected file."""
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
        test = entry.get("test")
        if not isinstance(test, str) or not test:
            raise PrimitiveError("a batch item has no test")
        inputs = entry["inputs"]
        actual = input_file(root, inputs, "actual", test)
        expected = input_file(root, inputs, "expected", test)
        items.append((test, actual, expected))
    return items


def input_file(root: Path, inputs: dict[str, object], name: str, test: str) -> Path:
    """Resolve a file input to a path, refusing anything outside `in/`."""
    value = inputs.get(name)
    if not isinstance(value, dict) or not isinstance(value.get("file"), str):
        raise PrimitiveError(f"the input named {name} of test {test} is not a file")
    path = (root / str(value["file"])).resolve()
    if not path.is_relative_to((root / "in").resolve()):
        raise PrimitiveError(f"the input named {name} of test {test} is outside in/")
    if not path.is_file():
        raise PrimitiveError(
            f"the input named {name} of test {test} is not in the working directory"
        )
    return path


def check(actual: Path, expected: Path) -> dict[str, object]:
    """Compare two files and return the outcome."""
    if same(actual, expected):
        return {"outcome": "accepted"}
    return {"outcome": "wrong_answer"}


def same(actual: Path, expected: Path) -> bool:
    """Whether two files match, ignoring trailing whitespace and trailing blank lines.

    The files are read in blocks of `BLOCK` bytes. Blocks that are the same
    byte for byte are passed over, so two identical files are compared at the
    speed of reading them. From the first blocks that differ, each file's
    lines have their trailing whitespace taken out (see `trimmed`) and the two
    trimmed streams are compared. Leaving out the same bytes from the start of
    both does not change the answer, even when they end inside a line: what is
    left of that line in each is compared, trimmed, as the whole line would
    be. Once one stream runs out, all that is left of the other must be
    newlines, which is what ignoring trailing blank lines means.
    """
    with actual.open("rb") as left, expected.open("rb") as right:
        while (a := left.read(BLOCK)) == (b := right.read(BLOCK)):
            if not a:
                return True
        ours, theirs = trimmed(a, left), trimmed(b, right)
        a = b = b""
        while True:
            a = a or next(ours, b"")
            b = b or next(theirs, b"")
            if not a or not b:
                break
            length = min(len(a), len(b))
            if a[:length] != b[:length]:
                return False
            a, b = a[length:], b[length:]
        rest, more = (a, ours) if a else (b, theirs)
        return not rest.strip(b"\n") and not any(block.strip(b"\n") for block in more)


def trimmed(first: bytes, stream: BinaryIO) -> Iterator[bytes]:
    """`first` and the rest of the stream with each line's trailing whitespace
    taken out, in non-empty blocks.

    The whitespace at the end of what has been read so far is held back, in
    the blocks it was read in, until the next byte that is not whitespace
    shows whether it ends a line: a newline drops it, anything else lets it
    through. At the end of the stream it is dropped.
    """
    held: list[bytes] = []
    start = (first,) if first else ()
    for block in chain(start, iter(lambda: stream.read(BLOCK), b"")):
        kept = block.rstrip(LINE_SPACE)
        if not kept:
            held.append(block)
            continue
        if held and not block.lstrip(LINE_SPACE).startswith(b"\n"):
            yield from held
        held = [block[len(kept) :]] if len(kept) < len(block) else []
        yield trim_lines(kept)


def trim_lines(data: bytes) -> bytes:
    """`data` with the whitespace before each of its newlines taken out.

    Each pass takes one whitespace byte from before every newline, searching
    and replacing at the speed of the bytes methods, so the usual one or two
    (a space, a carriage return) go in a pass or two. Whitespace still left
    after `TRIM_PASSES` passes is on lines longer than that, so there are few
    of them, and the data is then split into lines and each one trimmed.
    """
    for _ in range(TRIM_PASSES):
        ends = [end for end in LINE_ENDS if end in data]
        if not ends:
            return data
        for end in ends:
            data = data.replace(end, b"\n")
    return b"\n".join([line.rstrip(LINE_SPACE) for line in data.split(b"\n")])


def write_json(path: Path, document: dict[str, object]) -> None:
    """Write a JSON file whole: to a temporary name first, then renamed."""
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    partial.replace(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
