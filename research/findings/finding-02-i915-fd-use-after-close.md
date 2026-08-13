# Finding 02 — File-descriptor use-after-close in i915 native context `attach_resource` (guest→host)

> Status: HIGH-CONFIDENCE STATIC finding. Latent UAF-class bug on error paths. Direct sibling of
> the accepted upstream fix `54b362cd drm/panfrost: Avoid file descriptor use after close`
> ("the result could be an ioctl on a bad FD. Found and fixed by Claude Opus 4.8.").

## Target
- Project: **virglrenderer** (drm native context), file `src/drm/i915/i915_resource.c`,
  function `i915_renderer_attach_resource()`.
- Repo: https://gitlab.freedesktop.org/virgl/virglrenderer  Commit: `7fcfce4…` (HEAD, 2026-08-13).
- **i915 = Intel GPU driver** → reachable on Intel-graphics ChromeOS/Android(x86) hosts running
  crosvm/QEMU virtio-gpu DRM native context ⇒ potentially **ChromeOS/Android VRP relevant**
  (unlike Finding-01 which is asahi/Apple-only).

## Attacker input
A guest triggers resource attach of a DMABUF resource (virtio-gpu resource import), which drives
the host `i915_renderer_attach_resource()` import path.

## Vulnerable code (current HEAD)
```c
static int
gem_close(int fd, uint32_t handle)
{
   struct drm_gem_close close_req = { .handle = handle };
   return drmIoctl(fd, DRM_IOCTL_GEM_CLOSE, &close_req);   /* uses fd */
}
...
   ret = drmPrimeFDToHandle(dctx->fd, fd, &handle);
   ...
   off_t size = lseek(fd, 0, SEEK_END);
   close(fd);                          /* <-- fd is CLOSED here */
   if (size < 0) {
      drm_err(...);
      gem_close(fd, handle);           /* BUG: drmIoctl() on the CLOSED fd */
      return;
   }
   struct i915_object *obj = i915_object_create(handle, size);
   if (!obj) {
      gem_close(fd, handle);           /* BUG: drmIoctl() on the CLOSED fd */
      return;
   }
```

## Root cause / broken invariant
After `close(fd)`, the fd number is released and may be **reused** by any other thread in the
multi-threaded renderer (fence fds, other contexts, other imports). Both error paths then call
`gem_close(fd, handle)` → `drmIoctl(fd, DRM_IOCTL_GEM_CLOSE, ...)` on the stale/closed fd. The
correct handle-owning fd is `dctx->fd` (as the msm driver correctly uses, and as the accepted
panfrost fix `54b362cd` changed). Invariant: *never operate on a file descriptor after it is
closed*.

## Security primitive / impact
- Use-after-close of a file descriptor. If the fd number was reused (concurrently) to refer to a
  different DRM device / object fd, the `DRM_IOCTL_GEM_CLOSE` is delivered to the wrong fd →
  cross-context GEM handle close / ioctl on an unintended fd (resource confusion; potential double
  handling / UAF of GPU objects). Also leaks `handle` on the real `dctx->fd`.
- Boundary crossed: untrusted guest → host virglrenderer process.

## Reachability / severity (honest)
- The two buggy calls are on **error paths**: `lseek(fd, SEEK_END) < 0` (unlikely for a valid
  dmabuf just imported by `drmPrimeFDToHandle`) and `i915_object_create()==NULL` (calloc OOM). A
  guest cannot deterministically force these, so this is a **latent, low-severity** UAF rather
  than a directly weaponizable one. It is nonetheless a real fd-use-after-close and a 1:1 sibling
  of an accepted upstream fix, so it is correct to fix/report.

## Novelty check
- Unpatched at HEAD `7fcfce4`. msm already uses `dctx->fd` (correct); panfrost was fixed in
  `54b362cd`; i915 is the remaining un-fixed variant of the same class.

## Suggested fix (see finding-02-i915-fd-use-after-close.patch)
Replace `gem_close(fd, handle)` with `gem_close(dctx->fd, handle)` on both error paths.

## Related (minor) — asahi attach_resource
`src/drm/asahi/asahi_renderer.c` `asahi_renderer_attach_resource()`: on `lseek()<0` it logs but
does NOT return (proceeds to `asahi_object_create(handle, 0, size)` with a negative size), and on
`!obj` returns without `gem_close` (GEM handle leak). Not a UAF; noted for the upstream report.

## Disclosure route
Responsible disclosure upstream to virglrenderer (MR mirroring `54b362cd`), yielding fix + credit;
i915 reachability means it may additionally qualify under ChromeOS/Android VRP if a guest-triggerable
path to the error branch can be demonstrated on a Google product build.
