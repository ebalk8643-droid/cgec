# Findings index — virglrenderer drm native context (Phase-8 variant hunt)

Methodology (matches PLAN Phase 8): mine recently-landed security fixes in the drm native
context, extract the violated invariant, then hunt un-covered variants in the least-audited
drivers. The recent fixes were piecemeal per-driver (panfrost/msm/amdgpu), so the newest driver
(**asahi**, added in a single commit with zero security fixes) and error paths were prime suspects.

Commit studied: virglrenderer `7fcfce49616974dc7050fdbfb5bb915f4448d270` (HEAD, 2026-08-13).

## Confirmed candidates (static; ready-to-submit patches included)
| # | Bug | File / func | Class | Sibling fix | Reachability / value |
|---|-----|-------------|-------|-------------|----------------------|
| 01 | 32-bit `stride*count` overflow in length check → OOB read + missing calloc NULL-check | `asahi/asahi_renderer.c` `asahi_ccmd_vm_bind` | int-overflow / OOB (like panfrost `99409aae`) | `99409aae` | asahi (Apple-Silicon) hosts only → upstream CVE+credit, not VRP cash |
| 02 | fd use-after-close: `gem_close(fd,…)` after `close(fd)` on error paths | `i915/i915_resource.c` `i915_renderer_attach_resource` | UAF-of-fd (like panfrost `54b362cd`) | `54b362cd` | i915 (Intel) → ChromeOS/Android-relevant, but error-path/low-severity |

## Checked and found HARDENED (no bug)
- msm `gem_submit` (size_add/size_mul + `>hdr->len`), i915 `execbuffer2` (same), amdgpu `cs_submit`
  (size_mul + MAX + ring-id range), panfrost (fixed).
- ring-id/priority-as-index: i915 (`>=ARRAY_SIZE`), amdgpu (`>timeline_count`), asahi
  (`>NR_TIMELINES` with `[ring_idx-1]`, priority≤MAX at creation) — all correct.
- shared `drm_context.c`: response dispatch uses a shadow buffer + `drm_check_shm_bounds` +
  explicit double-fetch guard; `get_shmem_blob` blob_size validated (`8cb58e47`); munmap size no
  longer trusts guest (`9368c896`). Actively hardened by Google (chromium.org authors).
- asahi `ioctl_simple` (allow-list + `hdr->len==req_len` + payload cap), asahi `submit` (64-bit
  ptr math + `ptr>end`).

## Honest bottom line
Both findings are real, novel-looking, and 1:1 siblings of upstream-accepted fixes, but neither is
a high-value VRP-cash bug (asahi = Apple-only; i915 = error-path). Correct route = responsible
disclosure upstream to virglrenderer (fix + CVE + credit), the same path the sibling fixes took.
A cash-tier result needs the gated resources: a serious corpus-seeded fuzzing campaign on the
64 GB box (Intel/AMD/Mali drivers + venus/gfxstream) or the KVM/kvmCTF track.
