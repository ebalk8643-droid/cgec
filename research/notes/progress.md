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

### Next steps
- [ ] Static audit of `unsafe` in fresh/un-fuzzed surfaces, hunting the CVE-2026-53360-style
      pattern: guest-controlled length/count validated against a constant, not the real buffer.
      Priority: vhost_user handlers, gpu (virtio_gpu + rutabaga FFI), snd, media/video,
      descriptor_utils.rs, vm_memory volatile ops.
- [ ] Write structure-aware fuzz targets for the best candidates; run under ASan/UBSan.
- [ ] For any memory error: minimize, root-cause, prove guest reachability, novelty-check.
