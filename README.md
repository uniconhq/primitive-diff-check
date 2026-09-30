# primitive-diff-check

The `unicon/diff-check` primitive: it compares what a program printed with
the expected answer and gives an outcome and points for that test. It is the
last step of the `unicon/classic` workflow, after `unicon/compile` and
`unicon/sandbox-run`, and the outcome a verdict carries for a test that ran
comes from here.

This repo holds the image, `ghcr.io/uniconhq/primitive-diff-check`, built
from the `Dockerfile`; the program the image runs, `src/diff_check.py`; and
`primitive.yaml`, the declaration the forge compiler reads to type-check a
workflow that uses the primitive. The program is one Python file with no
dependencies. It speaks the primitive contract, `primitive.schema.json`
version 3, published by the [runner](https://github.com/uniconhq/runner).

## What it takes and returns

The primitive takes a batch (`batch: true`): one container compares every
test. Each item of the batch has these inputs and outputs.

| | Name | Type | What it is |
|---|---|---|---|
| Input | `actual` | file | What the program printed |
| Input | `expected` | file | The expected answer, from the task |
| Output | `outcome` | outcome | `accepted` when the two match, `wrong_answer` when they do not |
| Output | `points` | number | `1` when they match, `0` when they do not |

## When two files match

Two files match when they have the same lines once trailing whitespace
(spaces, tabs and carriage returns) is removed from the end of every line and
trailing blank lines are removed from the end of the file. So a missing final
newline, Windows line endings and stray spaces at line ends do not matter.
Leading whitespace, the spacing between words and blank lines between other
lines do.

The files are compared as bytes, line by line, so neither is held in memory
whole and no text encoding is assumed.

## Errors

`outputs.json` carries `error` instead, and nothing else, only when the
primitive could not work at all: `inputs.json` is missing, is not JSON or is
for another contract version, an item has no id or no inputs, or a file is
missing or lies outside `in/`. The harness turns an error into a
`system_error` verdict, so no contestant is graded by a broken step.

## Inside the sandbox

The harness starts the container with no network, a read-only root
filesystem, every capability dropped, `no-new-privileges`, Docker's built-in
seccomp profile and a non-root user; the image's user is 65532. The program
reads the files `inputs.json` names and writes only `/work/outputs.json`,
whole, under a temporary name first. The limits in `primitive.yaml` are per
test: 5 s of time and CPU, 256 MB of memory, 32 processes and 1 MB of output.

## Layout

```
Dockerfile                  the image: python:3.14-slim and the program
src/diff_check.py           the program, installed as /usr/local/bin/diff-check
primitive.yaml              the declaration, without the image line
scripts/check_declaration.py  checks primitive.yaml against the runner's schema
tests/                      unit tests, and image tests that run it on Docker
```

`primitive.yaml` has no `image` line here: bootstrap writes the image by
digest, from the release manifest, into the version it creates at the forge.

## Running it locally

Python 3.14 with [uv](https://docs.astral.sh/uv/), and Docker for the image
tests.

```
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run python scripts/check_declaration.py path/to/primitive.schema.json
uv run pytest
```

`uv run pytest` runs the unit tests and the image tests (marked `image`),
which build the image and run it under the harness's sandbox flags. Without
Docker the image tests are skipped. They use `PRIMITIVE_IMAGE` instead of
building when it is set. The declaration test and the checks on every
`inputs.json` and `outputs.json` the tests see read the schema from
`PRIMITIVE_SCHEMA`, or from a `runner` checkout beside this one.

CI runs the checks and unit tests in one job, against `primitive.schema.json`
from the runner release named in the workflow, and builds the image and runs
the image tests in another.

## Releasing

Push a tag `v1.2.3` on `main`. The release workflow refuses a tag whose
commit is not on `main`, a tag that differs from the version in
`pyproject.toml`, and a tag that is not a release of the version
`primitive.yaml` declares (`v1.2.3` is a release of `v1`). It runs the same
checks as CI, pushes the image as
`ghcr.io/uniconhq/primitive-diff-check:v1.2.3`, and creates a GitHub release
with `images.json`, which names the image by digest in the same shape as the
runner's, and `primitive.yaml` attached, and the digest in the notes.
`deploy/images.json` pins that digest, and bootstrap writes it into the
forge's copy of `primitive.yaml`.

The first push creates the package on the organisation as **private**.
Grading machines pull it anonymously, so someone has to open the package on
the organisation's Packages page once, set its visibility to public, and add
this repo under Manage Actions access so later releases can keep pushing to
it.
