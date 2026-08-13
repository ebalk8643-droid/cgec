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

### Session 3 — Phase-8 historical bug mining (drm native context) → FINDING
- Mined virglrenderer security fixes: a wave of guest-input-validation fixes landed in the drm
  native context (msm/panfrost/amdgpu), e.g. `99409aae drm/panfrost: Avoid reading past the end of
  the request` — the classic "guest count vs actual request length" OOB, fixed with overflow-safe
  `size_add(offsetof, size_mul(sizeof(elem), count))`. Fixes were piecemeal per-driver.
- Variant hunt across ALL drm drivers: msm gem_submit, i915 execbuffer2, amdgpu cs_submit,
  panfrost — all correctly use `size_mul`/`size_add` + `> hdr->len` checks (hardened). Other asahi
  handlers (ioctl_simple: allow-list + len check; submit: 64-bit ptr math) are OK.
- **FINDING-01 (findings/finding-01-*.md + .patch)**: `asahi_ccmd_vm_bind` uses a RAW 32-bit
  multiply `req->stride * req->count` (both u32) in its length check → integer overflow bypasses
  the check → loop `memcpy(&ops[i], payload + i*stride, stride)` reads far past the request buffer
  (OOB read); also missing `calloc` NULL-check → NULL-deref. Guest→host DoS / potential host-heap
  disclosure. Direct sibling of the accepted panfrost fix; asahi is the NEWEST driver
  (`f6052597`, added in one commit, zero security fixes). Ready-to-submit patch generated.
- HONEST caveats: reachable only on asahi (Apple-Silicon) hosts → NOT a ChromeOS/Android VRP cash
  bug; correct route = upstream responsible disclosure to virglrenderer (CVE + credit, like the
  sibling fixes). Static finding: cannot runtime-repro without Apple GPU.

### Session 3 — Phase-8 historical bug mining (drm native context) → FINDINGS
- Method: mine recent drm-native-context security fixes → hunt un-covered variants in least-audited
  drivers (asahi = newest, zero fixes). See findings/README.md for the full index.
- **FINDING-01**: `asahi_ccmd_vm_bind` raw 32-bit `stride*count` overflow → OOB read + missing
  calloc NULL-check (sibling of panfrost `99409aae`). Apple-only → upstream CVE, not VRP cash.
- **FINDING-02**: `i915_renderer_attach_resource` fd use-after-close `gem_close(fd,…)` after
  `close(fd)` (sibling of panfrost `54b362cd`). Intel/Google-relevant but error-path/low-severity.
- Verified HARDENED: msm/i915/amdgpu/panfrost count checks, ring-id/priority indexing (all
  drivers), shared drm_context.c response/shmem/blob/munmap paths, other asahi handlers.
- Both findings have ready-to-submit patches (findings/*.patch).

### Session 3 (final+) — crosvm virtio-video audit
- Audited all 12 `unsafe` in devices/src/virtio/video (highest-unsafe crosvm virtio surface, un-fuzzed):
  encoder ffmpeg `copy_nonoverlapping` has correct `packet_size > out_buf.size()` gate; mem_entry
  `from_raw_parts` is a size-matched union reinterpret; resource.rs:425 copy is in a #[test];
  vaapi/vda/fd blocks are mapping/descriptor-based. All SAFE. crosvm Rust remains hardened.
- CONCLUSION: every non-gated surface audited (crosvm Rust: virtqueue/video/gpu/descriptor_utils/
  flexible_array; virglrenderer: GL decode/vrend shader/venus ring/drm-native-context all drivers;
  rutabaga 2d) is hardened except the 2 drm-native-context findings already reported. Non-gated
  static vein is exhausted; further cash-tier progress is gated (64GB fuzzing / kvmCTF).

### Session 4 — Static Phase-8 on KVM (user's original kvmCTF inspiration)
- Blobless sparse-clone of torvalds/linux (HEAD 3d6d817), arch/x86/kvm.
- SEV #VMGEXIT/GHCB/PSC: the CVE-2026-53360 class was fixed by a WHOLE recent series —
  `db3f2195d293` (require in-GHCB scratch for GHCB v2+), `121d88de56bc` (check PSC indices vs actual
  buffer size), `c8cc238093ca`/`ce6ea7b33e00` (READ_ONCE / read indices once = TOCTOU), plus MMIO/
  PortIO length-0 and >8-byte rejects. This area is freshly hardened (opposite of un-audited).
- TDX (vmx/tdx.c, newer): `tdx_emulate_mmio` requires size∈{1,2,4,8}; `tdx_emulate_io` requires
  size∈{1,2,4}; `tdx_map_gpa` validates gpa+size overflow/legal/aligned; cpuid via r12/r13. All
  guest-controlled sizes validated. HARDENED (sibling of the SEV MMIO/PIO fixes already present).
- CONCLUSION: KVM guest→host (SEV+TDX confidential compute) is hardened; it is the most-scrutinized
  surface (KVM team + syzkaller + active SEV hardening series). No static candidate. Note: a KVM
  static finding would be CVE-tier only anyway — kvmCTF cash requires a RUNTIME exploit (needs a
  /dev/kvm host + SNP/TDX hardware), which is gated.

### Session 4 (cont.) — gfxstream static Phase-8 (Android AVF 3D backend)
- Blobless clone (HEAD d047a57). Mined host/ fixes: `bea594a4 Validate memory size on color buffer
  import` (ANB image path: image dims/mem vs imported ColorBuffer). Hunted siblings in the memory
  import paths (VkDecoderGlobalState VkAllocateMemory import): ColorBuffer/Buffer import derive
  `allocationSize` from HOST-tracked backing (`getBufferAllocationInfo`/getColorBufferInfo), not
  from guest values → guest can't over-request; staging read/write have `size > stagingBufferInfo.size`
  checks. Import paths SAFE.
- gfxstream guest-command decoding is largely auto-generated (VkDecoder, bounds-checked stream
  reads); real bugs there need build+fuzz of the guest command stream (gated / heavy — best on 64GB).

### Session 4 (cont.) — attempted to unlock deeper fuzzing (from_states)
- virgl_fuzzer_from_states requires inputs >=1024 bytes (else returns 0 — explains earlier cov:2 on
  tiny seeds). Built >=1024B seeds from valid command sequences.
- from_states then crashes at init: `failed to initialize vrend winsys` →
  `util_hash_table_get: Assertion 'ht' failed` (NULL ht after init failure). Its
  `testvirgl_init_ctx_cmdbuf(VIRGL_RENDERER_USE_EGL)` winsys path does NOT come up in this headless
  env (unlike virgl_fuzzer, which sets up its own EGL context via callbacks). This is a HARNESS/env
  limitation, NOT a virglrenderer bug (debug assert on init failure). Deeper from_states fuzzing is
  effectively GATED (needs a proper GL winsys — a box with a GPU or a fuller Mesa/EGL setup; best on
  the 64 GB box). virgl_fuzzer (cov ~765) remains the working campaign here.

### Session 5 — 64GB box (34.72.203.7) unblocked → RUNTIME-CONFIRMED finding
- SSH blocker was the GCP VPC firewall (`default-allow-ssh` limited to user IP + IAP); my egress is
  a rotating AWS NAT pool, so user opened tcp:22 to 0.0.0.0/0 (key-auth only). Connected.
- Box: instance-20260801-120110, 12 vCPU / 62 GB, Debian 13, NO /dev/kvm (n4) → Track A only.
  Root disk tiny (1.8G) → all work on /mnt/fuzz-data (196G). Installed clang-19/meson/ninja/GL deps.
- Built virglrenderer fuzzer (same SHA 7fcfce4) with coverage+ASan. from_states/drm_fuzzer NOT
  usable (no /dev/dri render node; vgem/vkms modules absent in cloud kernel) → virgl_fuzzer (GL) only.
- **Structure-aware TGSI generator** (research/scripts/gen_tgsi_shaders.py, 400 varied shaders):
  coverage 512 → 1231 → **1577**. 12-worker campaign then found crashes.
- **FINDING-04 (RUNTIME-CONFIRMED):** guest→host NULL-deref in `vrend_sync_shader_io`
  (vrend_renderer.c:4040) — `sub_ctx->shaders[prev_type]->current` deref'd while only the selector
  `prev` is NULL-checked. 100% reproducible (5/5) ASan SEGV @0x15c via a 218-byte malformed-TGSI
  command stream. repro-crash.bin + fix.patch in findings/finding-04/. Fix verified (rebuild → no
  crash). Guest→host DoS on the GL path (ChromeOS/Android relevant → strongest VRP/CVE candidate).
- Also 6 OOM artifacts (guest-controlled large allocs; lower value, not triaged as corruption).
- Applied the fix on the box, rebuilt, and RELAUNCHED the 12-worker campaign on the PATCHED binary
  + merged 400-shader TGSI corpus (corpus=939) to hunt deeper bugs past finding-04. Running.

### Next steps / decisions
- [x] Coverage-guided seeded virgl_fuzzer campaign running (cov 512→597+, corpus 118). One crash
      artifact found (crash-6faf792…) → **non-reproducible standalone (EXIT=0)** = NOT a bug
      (garbage cmd header, rejected as "Illegal command buffer"); saved under findings/non-repro/.
- [x] virgl_fuzzer_from_states built but does NOT init headless (cov 2, harness-init NULL SEGV, not
      a virglrenderer bug); needs GL-context wiring like virgl_fuzzer or a real GPU. Use virgl_fuzzer.
- [ ] Seed corpus for virgl_fuzzer (OSS-Fuzz corpus or virgl_fuzzer_from_states) → real coverage.
- [ ] Long, parallel, corpus-seeded virglrenderer campaign (needs more cores/RAM).
- [ ] Also build/fuzz gfxstream (other 3D backend) similarly.
- [ ] Audit snapshot/restore deserialization (fresh churn) as secondary.
- [ ] DECISION for user: (a) whitelist my egress IP **3.220.100.176** on the 64 GB box so I can
      run the serious virglrenderer campaign there; and/or (b) provide a nested-virt or bare-metal
      box to open the KVM/kvmCTF track. Both provided boxes are guest VMs (no /dev/kvm) — fine for
      Track A fuzzing, not for KVM.
