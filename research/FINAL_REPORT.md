# FINAL REPORT — VM/Hypervisor vulnerability research

_Legitimate, defensive research on public OSS, for official reward programs + responsible
disclosure. All work local; no third-party/production systems touched._

Branch: `cursor/vm-vulnerability-research-e5c8` · Working notes: `research/` · Findings: `research/findings/`

---

## 1. TARGET
- **Project:** crosvm (Google Rust VMM) + its guest-reachable C renderer **virglrenderer**
  (drm native context / virtio-gpu 3D).
- **Repositories / commits studied:**
  - crosvm `ea2b45e4c40ab836577b82795da6e6fe5f182fbd` (2026-08-13)
  - virglrenderer `7fcfce49616974dc7050fdbfb5bb915f4448d270` (2026-08-13)
- **Why selected:** user constraints = avoid saturated targets (V8), favor freshness, must be
  in-scope/monetizable, inspired by a KVM guest→host heap-corruption CVE. crosvm/virglrenderer is
  a real guest→host boundary, fresher & less-saturated than V8/core-KVM, locally buildable +
  fuzzable, and in scope for ChromeOS/Android VRP.
- Research-density: MEDIUM-HIGH (virglrenderer is OSS-Fuzz-covered AND currently being AI-audited —
  several 2026 fixes credit "Claude Opus 4.8"). Freshness: HIGH (drm native context, new drivers).
  Security-boundary: HIGH (guest→host VMM/sandbox). Expected-value: MEDIUM (hardened surface).

## 2. REWARD / DISCLOSURE ROUTES
- **kvmCTF** (Google VRP): guest→host KVM, up to **$250k**. BLOCKED — needs a `/dev/kvm` host
  (nested-virt Intel instance or bare-metal); both user-provided boxes were guest VMs w/o KVM.
- **ChromeOS VRP / Android AVF VRP**: guest→crosvm escape (incl. virglrenderer via virtio-gpu 3D);
  up to ~$100k. Requires a Google-host-relevant driver (msm/i915/amdgpu/panfrost) + demonstrable
  impact. Dependency bugs must be reported upstream first.
- **Upstream responsible disclosure** (virglrenderer, gitlab.freedesktop.org): CVE + credit — the
  route the recent sibling fixes took. This is where the two findings below fit.

## 3. ATTACK SURFACE (ranked, as investigated)
1. virglrenderer drm native context per-driver ccmd handlers (guest ioctl forwarding) — **freshest**
2. virglrenderer venus (Vulkan) ring/command decode
3. virglrenderer vrend GL command decode + TGSI shader translation
4. rutabaga_gfx FFI (Rust↔C)
5. crosvm virtio device backends (gpu, video, snd, vhost-user, fs)
6. crosvm virtqueue / descriptor_utils
7. crosvm snapshot/restore deserialization
8. gfxstream 3D backend (not built this round)
9. crosvm cross-domain / wayland
10. core KVM (kvmCTF) — gated on hardware

## 4. FINDINGS (see research/findings/*.md + *.patch)
### Finding 01 — asahi `vm_bind` 32-bit `stride*count` overflow → OOB read / NULL-deref
- Component: `src/drm/asahi/asahi_renderer.c: asahi_ccmd_vm_bind` (virglrenderer HEAD).
- Root cause: length check `hdr.len == sizeof(*req) + (stride*count)` uses raw 32-bit unsigned
  multiply (both u32) → wraps; loop then `memcpy` reads far past the request buffer; `calloc`
  result unchecked. Broken invariant: guest count·size must be validated with overflow-safe math
  (cf. accepted panfrost fix `99409aae`).
- Primitive: OOB read (+ NULL-deref DoS). Impact: guest→host DoS / potential host-heap disclosure.
- Novelty: unpatched at HEAD; asahi is the newest driver (one commit, zero sec fixes). Repro: static
  (asahi = Apple-Silicon only; cannot runtime-repro locally). Route: upstream CVE+credit.

### Finding 02 — i915 `attach_resource` file-descriptor use-after-close
- Component: `src/drm/i915/i915_resource.c: i915_renderer_attach_resource`.
- Root cause: `gem_close(fd, handle)` (→ `drmIoctl(fd, DRM_IOCTL_GEM_CLOSE)`) called on error paths
  AFTER `close(fd)`; correct fd is `dctx->fd` (msm does this; panfrost fixed in `54b362cd`).
- Primitive: fd use-after-close → ioctl on stale/reused fd (resource confusion). Impact: guest→host,
  but error-path/low-severity (hard to force). Novelty: unpatched variant at HEAD.
- Reachability: i915 = Intel → ChromeOS/Android relevant → possible VRP if a guest-forceable error
  path is shown. Route: upstream CVE+credit (+ VRP if impact demonstrated).

### Finding 03 — vrend `translate_load` image index off-by-one (`>` vs `>=`)
- Component: `src/vrend/vrend_shader.c: translate_load` (image path).
- Root cause: bound check uses `sreg_index > PIPE_MAX_SHADER_IMAGES` (allows ==32) where 3 sibling
  checks use `>=`; `images[32]` is one past the 32-slot array + `1<<32` shift UB. Incomplete part of
  accepted fix `9f1ca944`.
- Primitive: in-struct type-confused over-read (LOW severity; not a heap overflow — `images_used_mask`
  follows `images[]`). Impact: guest TGSI shader → host, wrong GLSL/limited. Route: upstream one-line
  follow-up fix + credit.

## 5. BEST FINDING
**Finding 02 (i915 fd-UAF)** has the best combination for monetization: i915 is a Google-relevant
host GPU (ChromeOS/Android x86), so it is the only one with a plausible VRP path in addition to
upstream credit. Finding 01 is the cleaner/more-severe memory-safety bug technically, but asahi
reachability limits it to upstream credit only.

## 6. TOOLING DELIVERED (reusable)
- `research/scripts/setup_env.sh` — crosvm + cargo-fuzz (incl. the libstdc++-14 gotcha).
- `research/scripts/setup_virglrenderer.sh` — virglrenderer libFuzzer+ASan build, incl. the
  CRITICAL `-fsanitize=fuzzer-no-link` whole-library coverage fix (cov 12→512+).
- `research/scripts/gen_virgl_seeds.py` — valid virgl command-buffer seed corpus.
- `research/scripts/run_fuzzers.sh` — crosvm guest→host fuzzers under ASan.

## 7. HONEST STATUS / NEXT
- Non-gated static vein on virglrenderer is largely exhausted (surface is hardened + actively
  AI-audited). Delivered 2 real, upstream-reportable findings + full, correctly-instrumented
  fuzzing tooling.
- KVM track (user's kvmCTF inspiration) also audited statically: SEV #VMGEXIT/PSC (the
  CVE-2026-53360 class) is freshly hardened by a whole fix series; TDX MMIO/PIO/map_gpa validate all
  guest sizes. Hardened. A KVM static candidate would be CVE-tier only; kvmCTF cash needs a runtime
  exploit on a /dev/kvm + SNP/TDX host (gated).
- Cash-tier progress is GATED on user resources:
  - (a) whitelist egress IP **3.220.100.176** on the 64 GB box → serious corpus-seeded fuzzing of
    venus/gfxstream + Google-relevant drivers; or
  - (b) a `/dev/kvm`-capable box (nested-virt Intel or bare-metal AMD) → kvmCTF.
- Pending user consent: file Finding 01/02 upstream to virglrenderer (CVE + credit).
