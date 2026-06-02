#!/usr/bin/env bash
# Optional entrypoint for ad-hoc use of the sandbox image. The runner passes an
# explicit `bash -lc "timeout N python ..."` command, so this is informational.
set -euo pipefail
exec "$@"
