#!/usr/bin/env bash
# Run crosvm guest→host fuzzers under ASan for a fixed duration.
# Usage: run_fuzzers.sh [SECONDS] [TARGET ...]
set -euo pipefail
CROSVM_DIR="${CROSVM_DIR:-$HOME/research/crosvm}"
DUR="${1:-1200}"; shift || true
TARGETS=("${@:-fs_server_fuzzer p9_tframe_fuzzer usb_descriptor_fuzzer qcow_fuzzer block_fuzzer}")
cd "$CROSVM_DIR"
for t in ${TARGETS[@]}; do
  mkdir -p "fuzz/corpus/$t"
  echo "[*] building $t"; cargo +nightly fuzz build "$t"
done
for t in ${TARGETS[@]}; do
  echo "[*] launching $t for ${DUR}s"
  ( cargo +nightly fuzz run "$t" -- -max_total_time="$DUR" -rss_limit_mb=3000 \
      -print_final_stats=1 > "/tmp/${t}_run.log" 2>&1 & )
done
echo "[*] launched. Tail /tmp/<target>_run.log ; crashes land in fuzz/artifacts/<target>/"
