#!/usr/bin/env bash
# Reproducible setup for crosvm vulnerability research (Track A).
# Tested on Ubuntu 24.04, x86_64. Idempotent-ish.
set -euo pipefail

CROSVM_DIR="${CROSVM_DIR:-$HOME/research/crosvm}"
CROSVM_SHA="${CROSVM_SHA:-ea2b45e4c40ab836577b82795da6e6fe5f182fbd}"

echo "[*] Installing system build deps..."
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  ninja-build meson libcap-dev libdrm-dev protobuf-compiler libssl-dev pkg-config \
  wayland-protocols libwayland-dev python3-pip g++ g++-13 \
  libstdc++-13-dev libstdc++-14-dev
# NOTE: on this image /usr/bin/c++ resolves to clang; clang selects GCC 14, so
# libstdc++-14-dev is REQUIRED or libfuzzer-sys fails with "'cstdint' file not found".

echo "[*] Rust nightly + cargo-fuzz..."
rustup toolchain install nightly --profile minimal
rustup component add rust-src --toolchain nightly
cargo +nightly install cargo-fuzz || true   # cargo-fuzz needs edition2024 (nightly)

echo "[*] Cloning crosvm @ ${CROSVM_SHA}..."
mkdir -p "$(dirname "$CROSVM_DIR")"
if [ ! -d "$CROSVM_DIR/.git" ]; then
  git clone --recurse-submodules https://github.com/google/crosvm.git "$CROSVM_DIR"
fi
git -C "$CROSVM_DIR" fetch --unshallow || true
git -C "$CROSVM_DIR" checkout "$CROSVM_SHA" || true
git -C "$CROSVM_DIR" submodule update --init --recursive

echo "[*] Smoke-build a fuzz target..."
( cd "$CROSVM_DIR" && cargo +nightly fuzz build virtqueue_fuzzer )

echo "[*] Done. Existing fuzz targets:"
ls -1 "$CROSVM_DIR/fuzz/fuzz_targets/"
