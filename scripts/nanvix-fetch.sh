#!/usr/bin/env bash
# Fetch and verify the pinned Nanvix Python microVM bundle.
#
# The bundle is a purpose-built microVM plus a purpose-built OS, not Linux.
# It has no conda-forge or PyPI package, so the release artifact is the
# supported distribution path.
#
# Everything lands in $SCRATCH, which is disposable by design: wipe it and
# the next run downloads and verifies the bundle again.

set -euo pipefail

NANVIX_TAG="3.12.3-nanvix-0.24.46-sdk.1-11739bd"
NANVIX_ASSET="nanvix-python-linux-x86-microvm-standalone-256mb.tar.gz"
NANVIX_SHA256="be9d14786c76bc99cc81c66b0d8aa6c8912cea252ab91941848b5ad3badaa259"
NANVIX_BASE_URL="https://github.com/nanvix/nanvix-python/releases/download/${NANVIX_TAG}"

# The release also publishes a dependency lock and a provenance record.
NANVIX_LOCK_SHA256="80e9a357980bd106881c87a7d4661f291bf579b12ef35756cd1a13617128fee2"
NANVIX_PROVENANCE_SHA256="950e63d7e35b67ae8bbf6bcdd212f50a098cfa7f06d9e5f09c4a7bc0cfcb164a"

SCRATCH="${SCRATCH:-${PIXI_PROJECT_ROOT:-$(pwd)}/scratch}"
ROOT="${SCRATCH}/nanvix-python"
DEST="${ROOT}/${NANVIX_TAG}"
ARCHIVE="${ROOT}/${NANVIX_ASSET}"

if [ ! -d "${SCRATCH}" ]; then
    mkdir -p "${SCRATCH}"
fi

verify() {
    local file="$1"
    local expected="$2"
    local actual
    actual="$(sha256sum "${file}" | cut -d ' ' -f 1)"
    if [ "${actual}" != "${expected}" ]; then
        echo "digest mismatch for ${file}" >&2
        echo "  expected ${expected}" >&2
        echo "  actual   ${actual}" >&2
        exit 1
    fi
    echo "digest ok: ${file}"
}

download() {
    local name="$1"
    local target="$2"
    if [ ! -f "${target}" ]; then
        echo "downloading ${name}"
        curl -sSL --fail --retry 3 -o "${target}.part" "${NANVIX_BASE_URL}/${name}"
        mv "${target}.part" "${target}"
    fi
}

if [ -x "${DEST}/bin/nanvixd.elf" ]; then
    echo "bundle already present: ${DEST}"
    exit 0
fi

mkdir -p "${ROOT}"

download "${NANVIX_ASSET}" "${ARCHIVE}"
verify "${ARCHIVE}" "${NANVIX_SHA256}"

download "nanvix.lock" "${ROOT}/nanvix.lock"
verify "${ROOT}/nanvix.lock" "${NANVIX_LOCK_SHA256}"

download "sdk-provenance.json" "${ROOT}/sdk-provenance.json"
verify "${ROOT}/sdk-provenance.json" "${NANVIX_PROVENANCE_SHA256}"

mkdir -p "${DEST}"
tar -xzf "${ARCHIVE}" -C "${DEST}" --strip-components=1

if [ ! -x "${DEST}/bin/nanvixd.elf" ]; then
    echo "extracted bundle has no bin/nanvixd.elf" >&2
    exit 1
fi

echo "bundle ready: ${DEST}"
