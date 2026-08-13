# Finding 01 — Integer overflow in asahi native-context `vm_bind` length check → OOB read / NULL-deref (guest→host)

> Status: HIGH-CONFIDENCE STATIC finding (code analysis definitive). NOT yet runtime-reproduced:
> the asahi native context only activates on hosts whose GPU uses the **asahi** kernel driver
> (Apple Silicon), which I cannot run locally. Reported honestly as a static candidate, in the
> same class as the recently-accepted sibling fixes (panfrost/msm/amdgpu) that were found by code
> review ("Found by Claude Opus 4.8. I adapted its fix.").

## Target
- Project: **virglrenderer** (drm native context) — the C renderer reachable from a guest via
  crosvm/QEMU virtio-gpu DRM native context.
- Repo: https://gitlab.freedesktop.org/virgl/virglrenderer
- Commit studied: `7fcfce49616974dc7050fdbfb5bb915f4448d270` (HEAD, 2026-08-13).
- File/function: `src/drm/asahi/asahi_renderer.c` → `asahi_ccmd_vm_bind()`.
- The asahi driver was added in a single commit `f6052597 drm: add asahi native-context
  implementation` and has received **no** security hardening (unlike msm/panfrost/amdgpu).

## Attacker input
A malicious guest submits an `ASAHI_CCMD_VM_BIND` command via the DRM native context.
Guest fully controls `hdr.len`, `stride`, `count`, and the `payload[]` bytes.

## Vulnerable code (current HEAD)
```c
static int
asahi_ccmd_vm_bind(struct drm_context *dctx, struct vdrm_ccmd_req *hdr)
{
   struct asahi_ccmd_vm_bind_req *req = to_asahi_ccmd_vm_bind_req(hdr);
   uint8_t *payload = (uint8_t *)req->payload;

   if (req->stride < offsetof(struct drm_asahi_gem_bind_op, offset)) { ... return -EINVAL; }

   /* BUG: req->stride and req->count are BOTH uint32_t, so the multiply is a
    * 32-bit unsigned operation that WRAPS mod 2^32. */
   if (req->hdr.len != (sizeof(*req) + (req->stride * req->count))) {
      drm_err("Invalid VM bind length");
      return -EINVAL;
   }

   struct drm_asahi_gem_bind_op *ops = calloc(req->count, req->stride);  /* BUG: no NULL check */
   ...
   for (unsigned i = 0; i < req->count; ++i) {
      memcpy(&ops[i], payload + (i * req->stride), req->stride);  /* OOB read of request buffer */
      ops[i].handle = handle_from_res_id(dctx, ops[i].handle);
   }
   ...
}
```
Types (confirmed): `struct asahi_ccmd_vm_bind_req { struct vdrm_ccmd_req hdr; uint32_t vm_id;
uint32_t stride; uint32_t count; uint8_t payload[]; }`, `vdrm_ccmd_req.len` is `uint32_t`.
`sizeof(*req) == 28`.

## Root cause / broken invariant
The length check is meant to enforce: `payload holds exactly count entries of stride bytes`
(`hdr.len == sizeof(*req) + count*stride`). But `req->stride * req->count` is evaluated in
**32-bit unsigned arithmetic** and can overflow. An attacker chooses `stride`, `count` so that
`(stride * count) mod 2^32` is small while the *true* product is ≥ 2^32, and sets `hdr.len =
sizeof(*req) + (wrapped small value)`. The check passes with a tiny request buffer, but the
loop then iterates `count` times reading `stride` bytes each = the true (huge) product, far past
the request buffer.

This is the exact class fixed for panfrost in `99409aae drm/panfrost: Avoid reading past the end
of the request`, which correctly uses the overflow-safe helpers
`size_add(offsetof(...), size_mul(sizeof(*elem), count))`. asahi uses raw `*` and was missed.

## Security primitive / impact
- Example: `stride = 8` (≥ offsetof, ok), `count = 0x20000000` → `8 * 0x20000000 = 2^32` wraps to
  `0`. Guest sets `hdr.len = 28`. Check `28 == 28 + 0` passes.
  - `calloc(0x20000000, 8) ≈ 4 GiB` → returns NULL on typical hosts → `memcpy(&ops[0], ...)`
    dereferences NULL → **SIGSEGV = guest→host DoS** of the renderer process (no NULL check).
  - On a large-RAM host where the 4 GiB calloc succeeds → the loop reads `payload + i*8` for
    ~5×10^8 iterations from a 28-byte request buffer → **massive OOB read of host heap** (walks
    off mapped memory → SIGSEGV, or copies adjacent host heap into `ops`, which is then handed to
    the kernel `DRM_IOCTL_ASAHI_VM_BIND`).
- Boundary crossed: untrusted guest → host virglrenderer process (crosvm GPU device / VMM).

## Reproduction (static; runtime needs Apple-Silicon host)
- Cannot be exercised by the headless llvmpipe fuzzer (that drives the GL/vrend path, not the DRM
  native context, and the asahi driver requires an Apple GPU). Runtime PoC requires a host with
  the asahi kernel driver + crosvm/QEMU virtio-gpu DRM native context selecting asahi.
- Code-level trigger is unambiguous (types + control flow above).

## Novelty check
- As of HEAD `7fcfce4` (2026-08-13) the function is unpatched; `git log -- asahi_renderer.c` shows
  only the initial add commit `f6052597`. Sibling drivers (msm/panfrost/amdgpu) already use
  `size_mul`/`size_add`; this is the un-fixed variant in the newest driver.

## Suggested fix (mirrors the accepted sibling fixes)
```c
size_t min_size = size_add(sizeof(*req), size_mul(req->stride, req->count));
if (req->hdr.len != min_size) { drm_err("Invalid VM bind length"); return -EINVAL; }
struct drm_asahi_gem_bind_op *ops = calloc(req->count, req->stride);
if (!ops) return -ENOMEM;   /* add missing NULL check */
```

## Disclosure route (honest)
- Reachability is limited to asahi (Apple-Silicon) hosts, so **not** a ChromeOS/Android VRP cash
  candidate. Correct route: **responsible disclosure upstream to virglrenderer** (GitLab issue /
  MR to gitlab.freedesktop.org/virgl/virglrenderer, security@), yielding a fix + CVE + credit —
  same path as the sibling panfrost/msm/amdgpu fixes. A one-line MR mirroring the panfrost fix is
  appropriate.
