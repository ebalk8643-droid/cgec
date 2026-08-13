# Research progress log

## 2026-08-13 — Session 1

### Environment
- Working box: cloud agent env (Ubuntu 24.04, 4 vCPU, 15 GB RAM, 235 GB disk, passwordless sudo).
- User-provided 64 GB GCE box (34.72.203.7) is currently UNREACHABLE: SSH blocked by host-side
  IP allowlist (my egress IP 3.220.100.176 not permitted; TCP:22 connects then RST before banner).
  ACTION for user: whitelist 3.220.100.176 on that box (hosts.allow / sshd Match / firewall) to
  move heavy fuzzing there. Meanwhile Track A runs locally (fuzzers don't need /dev/kvm).

### Toolchain gotchas (resolved)
- `cargo install cargo-fuzz` needs edition2024 → install via `cargo +nightly install cargo-fuzz`.
- `/usr/bin/c++` = clang here; clang picks GCC 14 → need `libstdc++-14-dev` or libfuzzer-sys
  fails: `'cstdint' file not found`.

### crosvm baseline
- SHA `ea2b45e4c40ab836577b82795da6e6fe5f182fbd` (2026-08-13). Submodules: depot_tools, minijail, perfetto.
- Existing fuzz targets (well-covered by OSS-Fuzz): block, fs_server, p9_tframe, qcow,
  usb_descriptor, virtqueue, zimage.
- **Un-fuzzed surfaces (no dedicated target)** = higher novelty EV: gpu (virtio-gpu 2D/3D +
  rutabaga), media/video, snd, net, scsi, vsock, wl, iommu, balloon, pmem, and the vhost-user
  protocol handlers.

### Freshness (churn in devices/src/virtio, last 12 months — top)
1. vhost_user_backend/handler.rs (22)   2. vhost_user_frontend/mod.rs (17)
3. fs/passthrough.rs (15)               4. gpu/mod.rs (10)   5. gpu/virtio_gpu.rs (8)
6. vhost_user_frontend/handler.rs (7)   7. vhost_user_backend/vsock.rs (6)
8. snd/common_backend (5)               9. gpu/edid.rs (5)   10. media.rs (4)
- Heavy recent theme: **rutabaga_gfx / virtio_gpu snapshot-restore** (deserialization of device
  state — classic fresh attack surface).

### Triage: virtqueue_fuzzer crash (NOT a vuln)
- Immediate crash → Rust **panic** at `devices/src/virtio/queue/split_queue.rs:336` (peek()
  region; `get_slice_at_addr(...).unwrap()` family). SIGABRT, not an ASan memory error.
- Classification: Type 1/2 (memory-safe panic). At most a guest-triggerable DoS of the device
  process; almost certainly already known to OSS-Fuzz. NOT escalating.

### Audit results (see findings/audit-crosvm-session1.md)
- Repo-wide sweep of memory-corruption sinks (from_raw_parts/set_len/copy_nonoverlapping/ptr.add).
- Triaged hot candidates: rutabaga 2D transfer, video mem_entry cast, GpuCommand::decode,
  flexible_array set_len → ALL well-hardened (bounded Reader/.get()/checked_arithmetic!/clamping).
- Ran guest→host fuzzers fs_server (~90k/s) + p9 (~52k/s) under ASan: coverage plateaued (OSS-Fuzz
  corpus exhaustive), 0 crashes. Only crash = earlier virtqueue **panic** (DoS, likely known).
- SYSTEMIC CONCLUSION: crosvm in-tree Rust neutralizes the classic count-vs-buffer OOB. Real
  memory-corruption EV is in the C deps (virglrenderer/gfxstream via virtio-gpu 3D, cf.
  CVE-2025-2509) — NOT in this repo — or in rare unsafe/snapshot-restore deserialization.

### UPDATE: working fuzzer on the REAL surface (virglrenderer C, guest→host 3D)
- Built `virglrenderer` (freedesktop, SHA 7fcfce49616974dc7050fdbfb5bb915f4448d270) + its upstream
  `virgl_fuzzer` under clang ASan+libFuzzer. Runs headless via Mesa llvmpipe (surfaceless EGL).
- This is the genuine memory-corruption target reachable guest→host via crosvm virtio-gpu 3D
  (same component family as CVE-2025-2509). Reproducible recipe: scripts/setup_virglrenderer.sh.
- Build gotchas solved: need `libclang-rt-18-dev` (asan runtime); build STATIC
  (`-Ddefault_library=static -Db_lundef=false`) so asan symbols resolve into the fuzzer exe.
- Current run: ~14 exec/s, cov shallow (12) — random input rejected as "Illegal command buffer".
  NEEDS a seed corpus of valid virgl command streams (OSS-Fuzz corpus / virgl_fuzzer_from_states)
  for meaningful depth. Best run as a long, parallel, corpus-seeded campaign on the 64 GB box.
- This is now the PRIMARY high-EV target for Track A.

### Session 2 additions
- venus (Vulkan renderer, src/venus/) audit: ring/region setup (`vkr_ring.c`/`vkr_transport.c`)
  uses `vkr_region` with is_valid(overflow)/is_within/is_disjoint/aligned/power-of-two checks —
  well-hardened. `get_resource_pointer` guarded only by assert (NDEBUG!), but callers validate via
  regions. No bug found by reading. GL decode handlers (`vrend_decode.c`) all length-check before
  indexing. Conclusion: virglrenderer core is also hardened + OSS-Fuzz-saturated.
- **CRITICAL fuzzing fix**: the initial virgl_fuzzer build only instrumented the harness file
  (cov ~12 = BLIND fuzzing). Rebuilt with `-Dc_args/-Dcpp_args=-fsanitize=fuzzer-no-link` so the
  WHOLE library is coverage-instrumented → cov jumps to 512+. Now genuinely coverage-guided.
- Added `research/scripts/gen_virgl_seeds.py` (valid virgl command-buffer seeds). Input format:
  raw u32 command buffer fed to virgl_renderer_submit_cmd (FuzzMode1 pre-creates resource 10).
- This properly-instrumented, seeded, ASan coverage-guided fuzzer on the real guest→host surface
  is the key reusable asset. Serious campaign belongs on the 64 GB box (more cores + OSS-Fuzz
  corpus + fresh venus/video coverage).

### Next steps / decisions
- [ ] Seed corpus for virgl_fuzzer (OSS-Fuzz corpus or virgl_fuzzer_from_states) → real coverage.
- [ ] Long, parallel, corpus-seeded virglrenderer campaign (needs more cores/RAM).
- [ ] Also build/fuzz gfxstream (other 3D backend) similarly.
- [ ] Audit snapshot/restore deserialization (fresh churn) as secondary.
- [ ] DECISION for user: (a) whitelist my egress IP **3.220.100.176** on the 64 GB box so I can
      run the serious virglrenderer campaign there; and/or (b) provide a nested-virt or bare-metal
      box to open the KVM/kvmCTF track. Both provided boxes are guest VMs (no /dev/kvm) — fine for
      Track A fuzzing, not for KVM.
