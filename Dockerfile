# The diff-check primitive, ghcr.io/uniconhq/primitive-diff-check. One
# container per batch of tests: it reads /work/inputs.json and the two files of
# every test under /work/in/, and writes /work/outputs.json.

# Pinned by digest so a release rebuilds from the same base. python:3.14-slim
# (Debian 13), pulled 2026-09-13, the same pin as the runner's images and the
# other two primitives. Bump it from
# `docker image inspect python:3.14-slim --format '{{index .RepoDigests 0}}'`.
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

LABEL org.opencontainers.image.title="primitive-diff-check" \
      org.opencontainers.image.description="The Unicon diff-check primitive: compare an output with the expected one." \
      org.opencontainers.image.source="https://github.com/uniconhq/primitive-diff-check" \
      org.opencontainers.image.licenses="MIT"

COPY --chmod=0755 src/diff_check.py /usr/local/bin/diff-check

# The harness runs every step as a non-root user with a read-only root, and
# /work and /tmp as the only writable places. The program writes only
# /work/outputs.json.
USER 65532:65532
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/diff-check"]
