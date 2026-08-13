#!/usr/bin/env bash
# Build the REAL guest->host memory-corruption surface: virglrenderer + its upstream
# libFuzzer harness, under AddressSanitizer, runnable headless via Mesa llvmpipe.
# virglrenderer is the C renderer reachable from a guest through crosvm virtio-gpu 3D
# (cf. CVE-2025-2509). In scope for ChromeOS VRP (report upstream dep first).
set -euo pipefail
VIRGL_DIR="${VIRGL_DIR:-$HOME/research/virglrenderer}"

echo "[*] Deps (GL/EGL/DRM/gbm + clang asan runtime + check)..."
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  meson ninja-build clang libclang-rt-18-dev \
  libepoxy-dev libdrm-dev libgbm-dev libegl-dev libgles-dev mesa-common-dev \
  libgl1-mesa-dri libegl-mesa0 check

if [ ! -d "$VIRGL_DIR/.git" ]; then
  git clone --depth 50 https://gitlab.freedesktop.org/virgl/virglrenderer.git "$VIRGL_DIR"
fi
cd "$VIRGL_DIR"

echo "[*] Configure (clang + ASan + libFuzzer, STATIC libs so asan rt links into fuzzer)..."
rm -rf build-fuzz
# Key flags:
#  -Ddefault_library=static  -> avoids undefined __asan_* in shared libvirglrenderer.so
#  -Db_lundef=false          -> tolerate asan symbols resolved at final link
CC=clang CXX=clang++ meson setup build-fuzz \
  -Dfuzzer=true -Dtests=true -Db_sanitize=address -Db_lundef=false \
  -Ddefault_library=static -Dbuildtype=debugoptimized

echo "[*] Build fuzzers..."
ninja -C build-fuzz tests/fuzzer/virgl_fuzzer || true
ninja -C build-fuzz tests/fuzzer/virgl_fuzzer_from_states || true

cat <<'EOF'
[*] Done. Run headless (software GL) e.g.:
  export EGL_PLATFORM=surfaceless LIBGL_ALWAYS_SOFTWARE=1 \
         GALLIUM_DRIVER=llvmpipe MESA_LOADER_DRIVER_OVERRIDE=llvmpipe \
         ASAN_OPTIONS=detect_leaks=0
  ./build-fuzz/tests/fuzzer/virgl_fuzzer -jobs=$(nproc) -workers=$(nproc) \
       -rss_limit_mb=4096 <corpus_dir>

NOTE: needs a SEED CORPUS of valid virgl command streams for meaningful coverage
(random bytes are rejected as "Illegal command buffer"). Pull the OSS-Fuzz virgl_fuzzer
corpus, or use virgl_fuzzer_from_states with recorded GL states. Best run long-term on
the 64 GB box (more cores/RAM + full corpus).
EOF
