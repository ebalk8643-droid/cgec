# Ready-to-submit upstream disclosure drafts (virglrenderer)

These are prepared for one-click submission **once the user explicitly approves**. Nothing here
has been sent. Target project: virglrenderer (https://gitlab.freedesktop.org/virgl/virglrenderer).
Both are the same class as recently-accepted fixes in the drm native context.

Reporting mechanics (for when approved):
- File a **confidential** issue on gitlab.freedesktop.org/virgl/virglrenderer (Issues → mark
  "This issue is confidential") OR email the maintainers; then open an MR with the patch.
- The recent sibling fixes (`99409aae`, `54b362cd`, `375e6cb9`, `9368c896`) were handled as normal
  MRs referencing the class; follow the same flow. Patches: `finding-01-*.patch`, `finding-02-*.patch`.

---

## DRAFT 1 — asahi native context: integer overflow in `vm_bind` length check

**Title:** drm/asahi: overflow in `asahi_ccmd_vm_bind` length check → OOB read + missing calloc NULL-check

**Summary:**
`asahi_ccmd_vm_bind()` validates the request length with a raw 32-bit multiply:
```c
if (req->hdr.len != (sizeof(*req) + (req->stride * req->count))) { ... }
```
`req->stride` and `req->count` are both `uint32_t`, so `stride * count` is computed in 32-bit
unsigned arithmetic and can wrap mod 2^32. A guest can pick `stride`/`count` whose true product is
≥ 2^32 while the wrapped value is small, set `hdr.len = sizeof(*req) + <wrapped>`, and pass the
check with a tiny request buffer. The subsequent loop
```c
for (i = 0; i < req->count; ++i)
    memcpy(&ops[i], payload + (i * req->stride), req->stride);
```
then reads far past the request buffer (heap OOB read). Additionally `calloc(req->count,
req->stride)` is used without a NULL check, so the huge (real-size) allocation returning NULL leads
to a NULL-pointer write (`memcpy(&ops[0], ...)`).

**Impact:** guest → host (virglrenderer process) OOB read / NULL-deref DoS; potential host-heap
disclosure into the `DRM_IOCTL_ASAHI_VM_BIND` payload. Same class as `99409aae drm/panfrost: Avoid
reading past the end of the request`; asahi is the newest driver and lacks the overflow-safe check.

**Affected:** current HEAD; introduced by `f6052597 drm: add asahi native-context implementation`.

**Fix:** use the overflow-safe helpers and check the allocation (see finding-01 patch):
```c
if (req->hdr.len != size_add(sizeof(*req), size_mul(req->stride, req->count))) return -EINVAL;
struct drm_asahi_gem_bind_op *ops = calloc(req->count, req->stride);
if (!ops) return -ENOMEM;
```

---

## DRAFT 2 — i915 native context: file-descriptor use-after-close in `attach_resource`

**Title:** drm/i915: fd use-after-close in `i915_renderer_attach_resource` error paths

**Summary:**
In `i915_renderer_attach_resource()` the dmabuf import fd is closed, then used on error paths:
```c
off_t size = lseek(fd, 0, SEEK_END);
close(fd);                       /* fd closed */
if (size < 0) { ...; gem_close(fd, handle); return; }        /* uses closed fd */
struct i915_object *obj = i915_object_create(handle, size);
if (!obj) { gem_close(fd, handle); return; }                 /* uses closed fd */
```
`gem_close()` does `drmIoctl(fd, DRM_IOCTL_GEM_CLOSE, ...)` on the already-closed `fd`. In the
multi-threaded renderer the fd number may be reused before/at this point, so the ioctl can be
delivered to an unrelated fd (resource confusion / GEM handle close on the wrong device). The
handle-owning fd is `dctx->fd` (as the msm driver already uses). Same class as `54b362cd
drm/panfrost: Avoid file descriptor use after close`.

**Impact:** guest → host; use-after-close of a file descriptor. Currently reachable only on the two
error paths (lseek<0 / calloc failure), so latent/low-severity, but a correctness UAF worth fixing.

**Affected:** current HEAD.

**Fix:** use `dctx->fd` (see finding-02 patch):
```c
gem_close(dctx->fd, handle);   /* both error paths */
```
(Also: asahi `attach_resource` leaks the GEM handle on `!obj` and proceeds with a negative `size`
on `lseek<0`; worth tidying in the same series.)

---

## DRAFT 3 — vrend translate_load image index off-by-one (`>` vs `>=`)

**Title:** vrend/shader: use `>=` for image index bound in translate_load (follow-up to 9f1ca944)

**Summary:**
`translate_load()` checks the image register index with `>` where the sibling checks use `>=`:
```c
if (sinfo->sreg_index < 0 || sinfo->sreg_index > PIPE_MAX_SHADER_IMAGES)   /* allows == 32 */
    return false;
...
if (!((1 << sinfo->sreg_index) & ctx->images_used_mask))   /* 1 << 32 : shift UB on uint32_t */
    return false;
... ctx->images[sinfo->sreg_index] ...                     /* images[32]: images[] has 32 slots */
```
`PIPE_MAX_SHADER_IMAGES == 32` and `images[]` has 32 entries (valid 0..31). A guest TGSI shader
with an image load at index 32 (and image 0 declared) passes the check, causes `1 << 32` UB, and
reads `ctx->images[32]` (one past the array; `images_used_mask` and following struct fields are
mis-read as a `vrend_shader_image`). Low severity (in-struct over-read, not a heap overflow), but a
clear off-by-one and incomplete part of `9f1ca944`. The other three sites (3822/3882/4166) already
use `>=`.

**Fix (finding-03 patch):** change `>` to `>=`.

## Not-included (verified safe / non-bugs)
Per Phase-8 review, the following were checked and are hardened (do NOT report): msm/i915/amdgpu/
panfrost count-vs-len checks (size_mul/size_add), ring-id/priority indexing (all drivers), shared
`drm_context.c` response/shmem/blob/munmap handling, vrend sampler/image indexing, venus ring
regions, KVM SEV #VMGEXIT/PSC (freshly fixed) and TDX MMIO/PIO/map_gpa, gfxstream import paths.
