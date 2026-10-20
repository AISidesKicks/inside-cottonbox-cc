#!/usr/bin/env bash
# Run a Python workload inside the Nanvix microVM guest.
#
# usage:
#   scripts/nanvix-run.sh script.py        run a Python file as the workload
#   scripts/nanvix-run.sh --shell           drop into the interactive REPL
#   scripts/nanvix-run.sh --exec "code"     run a one-liner
#
# The workload is copied into the bundle's mnt/ directory, which the guest
# sees at /mnt. The guest then picks it up as mnt/bootstrap.py.

set -euo pipefail

NANVIX_TAG="3.12.3-nanvix-0.24.46-sdk.1-11739bd"
SCRATCH="${SCRATCH:-${PIXI_PROJECT_ROOT:-$(pwd)}/scratch}"
BUNDLE="${SCRATCH}/nanvix-python/${NANVIX_TAG}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -x "${BUNDLE}/bin/nanvixd.elf" ]; then
    "${HERE}/nanvix-fetch.sh"
fi

MODE="script"
WORKLOAD=""

case "${1:-}" in
    --shell)
        MODE="shell"
        ;;
    --exec)
        MODE="exec"
        WORKLOAD="${2:-}"
        ;;
    "")
        echo "usage: $(basename "$0") <script.py> | --shell | --exec \"code\"" >&2
        exit 2
        ;;
    *)
        MODE="script"
        WORKLOAD="$1"
        ;;
esac

# The guest picks the first of these that exists: bootstrap.py, then argv.txt.
rm -f "${BUNDLE}/mnt/argv.txt"

case "${MODE}" in
    script)
        cp "${WORKLOAD}" "${BUNDLE}/mnt/bootstrap.py"
        ;;
    exec)
        printf '%s\n' "${WORKLOAD}" > "${BUNDLE}/mnt/bootstrap.py"
        ;;
    shell)
        rm -f "${BUNDLE}/mnt/bootstrap.py"
        ;;
esac

cd "${BUNDLE}"
exec ./bin/nanvixd.elf \
    -ramfs nanvix_rootfs.img \
    -mount ./mnt \
    -- python3.initrd
