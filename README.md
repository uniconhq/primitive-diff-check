# primitive-diff-check

The `unicon/diff-check` primitive: it compares what a program printed with
the expected answer and gives the outcome for that test. It is the last step
of the `unicon/classic` workflow, after `unicon/compile` and
`unicon/sandbox-run`, and the outcome a test that ran carries in the result
comes from here.

This repo holds the image, `ghcr.io/uniconhq/primitive-diff-check`, built
from the `Dockerfile`; the program the image runs, `src/diff_check.py`; and
`primitive.yaml`, the declaration the forge compiler reads to type-check a
workflow that uses the primitive. The program is one Python file with no
dependencies. It speaks the primitive contract, `primitive.schema.json`
version 5, published by the [runner](https://github.com/uniconhq/runner).

## What it takes and returns

The primitive takes a batch (`batch: true`): one container compares every
test. A batch item and its answer in `outputs.json` are keyed by `test`, the
test's id as the plan writes it, `<group>/<test>`, and the answers come in the
order of the items. Each item has these inputs and outputs.

| | Name | Type | What it is |
|---|---|---|---|
| Input | `actual` | file, `runs: false` | What the program printed |
| Input | `expected` | file, `runs: false` | The expected answer, from the task |
| Output | `outcome` | outcome | `accepted` when the two match, `wrong_answer` when they do not |

Both inputs are files it reads as data: it runs nothing from either, so
handing it a task file the contestant is not served seals no step. It writes
no files of its own, only `outputs.json`.

The outcome is all it gives back. With no `credit` in `task.yaml`, an accepted
test earns credit 1 and any other test 0; what a test is worth is the
business of the task's test groups, through their `each`, `worst` and `pass`
weights.

## When two files match

Two files match when they have the same lines once trailing whitespace
(spaces, tabs, carriage returns, vertical tabs and form feeds) is removed
from the end of every line and
trailing blank lines are removed from the end of the file. So a missing final
newline, Windows line endings and stray spaces at line ends do not matter.
Leading whitespace, the spacing between words and blank lines between other
lines do.

The files are compared as bytes, in blocks of 1 MB, so neither is held in
memory whole and no text encoding is assumed. Blocks that are the same byte
for byte are passed over; from the first that differ, the whitespace before
each newline is taken out with the bytes methods' search and replace, a
pass for each byte of the longest such run up to four, and the few lines
with longer runs are then trimmed one by one. Nothing is done line by line
in Python for ordinary output, and the time is linear in the size of the
files whatever their lines look like.

## Errors

`outputs.json` carries `error` instead, and nothing else, only when the
primitive could not work at all: `inputs.json` is missing, is not JSON or is
for another contract version, an item has no test or no inputs, or a file
is missing or lies outside `in/`. The harness turns an error into a
`system_error` that stops the run, so no contestant is graded by a broken step.

## Inside the sandbox

The harness starts the container with no network, a read-only root
filesystem, every capability dropped, `no-new-privileges`, Docker's built-in
seccomp profile and a non-root user; the image's user is 65532. The program
reads the files `inputs.json` names and writes only `/work/outputs.json`,
whole, under a temporary name first. `primitive.yaml` declares no network
(`network: false`), and its limits are per test: 2 s of time and CPU, 256 MB
of memory, 32 processes, 1 MB of output and no GPUs. The `forge` repo's
compiler adds up time and CPU over the tests of the batch, so the container
has the program's start, well under a second, besides. The 2 s cover the
largest comparison. Measured in the image with one CPU on a loaded laptop on
which Python ran several times slower than usual: two identical 32 MB
outputs took 0.05 s; a 32 MB output whose every line ends in a carriage
return or a space 0.8 to 1.9 s; and the worst shape, every line ending in
five or more whitespace bytes, 3.5 to 3.9 s, about a second on ordinary
hardware. Outputs of ordinary size take milliseconds.

## Layout

```
Dockerfile                  the image: python:3.14-slim and the program
src/diff_check.py           the program, installed as /usr/local/bin/diff-check, the image's entrypoint
primitive.yaml              the declaration, without the image line
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
uv run python ../runner/scripts/check_declaration.py ../runner/schemas/primitive.schema.json .
uv run pytest
```

The declaration check is the runner's, so it runs from a `runner` checkout
beside this one, at the release named in `.github/workflows/ci.yaml`.

`uv run pytest` runs the unit tests and the image tests (marked `image`),
which build the image and run it under the harness's sandbox flags. Without
Docker the image tests are skipped. They use `PRIMITIVE_IMAGE` instead of
building when it is set. The checks on every
`inputs.json` and `outputs.json` the tests see read the schema from
`PRIMITIVE_SCHEMA`, or from a `runner` checkout beside this one.

`.github/workflows/ci.yaml` and `release.yaml` call the workflows every
primitive shares, `primitive-ci.yaml` and `primitive-release.yaml` in the
[runner](https://github.com/uniconhq/runner) repo, at the runner release this
primitive is built against, and name the same release as `runner-ref`. They
check this repo out beside the runner at that release, so the checks read
its `primitive.schema.json` and run its `scripts/check_declaration.py`. CI
runs the checks and unit tests in one job, and builds the image and runs the
image tests in another. Moving to a new runner release is a change to the
two `uses:` lines and `runner-ref` together.

## Releasing

Push a tag `v2.0.0` on `main`. The shared release workflow refuses a tag whose
commit is not on `main` and a tag that differs from the version in
`pyproject.toml`. The tag's major is the version at the forge: `v2.0.0` and
`v2.1.0` are both `unicon/diff-check@v2`, and a change to the ports is a new
major; `primitive.yaml` names no version of its own. The workflow runs the
same checks as CI, pushes the image as
`ghcr.io/uniconhq/primitive-diff-check:v2.0.0`, and creates a GitHub release
with `images.json`, which names the image by digest in the same shape as the
runner's, and `primitive.yaml` attached, and the digest in the notes.
`deploy/images.json` pins that digest, and bootstrap writes it into the
forge's copy of `primitive.yaml`.

The first push creates the package on the organisation as **private**.
Grading machines pull it anonymously, so someone has to open the package on
the organisation's Packages page once, set its visibility to public, and add
this repo under Manage Actions access so later releases can keep pushing to
it.
