#!/usr/bin/env bash
set -euo pipefail
case ${LIBRETTO_RAM_MB:-20} in
    20|32) ;;
    *) echo 'LIBRETTO_RAM_MB must be 20 or 32.' >&2; exit 2 ;;
esac
exec qemu-system-i386 -cpu pentium -m "${LIBRETTO_RAM_MB:-20}" \
    -nic none -monitor none -serial none "$@"
