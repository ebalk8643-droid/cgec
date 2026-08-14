# Finding 05 — Second NULL-deref in vrend `vrend_sync_shader_io` (next-stage block) — guest→host DoS

> Status: **RUNTIME-CONFIRMED** (ASan SEGV, reproducible). Sibling of finding-04 in the SAME
> function but the *next-stage* code path — found by the fork-mode campaign after finding-04 was
> patched (proving the patched build let the fuzzer reach deeper). The comprehensive fix
> (`finding-04/fix-comprehensive.patch`) resolves finding-04 AND finding-05.

## Target
- virglrenderer `src/vrend/vrend_renderer.c`, `vrend_sync_shader_io()` (next-stage block, line ~4134).
- Commit `7fcfce4…`. Guest→host via a crafted TGSI shader command stream (GL path).

## Crash (AddressSanitizer)
```
AddressSanitizer: SEGV on unknown address 0x0000000000000010
 #1 __asan_memcpy
 #2 vrend_sync_shader_io      src/vrend/vrend_renderer.c:4134:42
 #3 vrend_fill_shader_key     src/vrend/vrend_renderer.c:4319
 #4 vrend_shader_select       src/vrend/vrend_renderer.c:4381
 #5 vrend_finish_shader / vrend_shader_assign_tgsi / vrend_create_shader
 #8 vrend_decode_create_shader src/vrend/vrend_decode.c:136
```
Reproducer: `finding-05/repro-crash.bin` (549 bytes), 100% reproducible.

## Root cause
In the `next_type` handling of `vrend_sync_shader_io`:
```c
struct vrend_shader *fs = sub_ctx->shaders[PIPE_SHADER_FRAGMENT]->current;
key->fs_info = fs->var_sinfo.fs_info;   /* struct copy => memcpy; fs (->current) may be NULL */
```
plus the adjacent
```c
if (next_type != PIPE_SHADER_FRAGMENT) {
   key->num_out_clip = sub_ctx->shaders[next_type]->current->var_sinfo.num_in_clip;  /* ->current unchecked */
   ...
}
```
As in finding-04, `->current` (the compiled variant of a bound stage shader) can be NULL when the
guest binds a stage shader without a successfully-compiled/selected variant. `key->fs_info =
fs->var_sinfo.fs_info` is a structure copy → `memcpy` reads from `NULL + 0x10` → SEGV.

## Impact
Guest→host NULL-pointer dereference → host renderer crash (DoS). Same class/severity as finding-04
(not memory corruption; fixed NULL+offset). `vrend_sync_shader_io` had a **cluster** of unchecked
`->current` derefs (prev block = finding-04; next block = finding-05).

## Fix
`finding-04/fix-comprehensive.patch` guards all three `->current` dereferences in the function (prev
block + next-stage clip/cull + `fs`). Verified: both finding-04 and finding-05 reproducers no longer
crash after the comprehensive patch (rebuild → exit 0).

## Disclosure
Fold into the finding-04 upstream report: submit the **comprehensive** patch (covers the whole
`vrend_sync_shader_io` `->current` cluster) rather than the partial one. Guest→host DoS, GL path.
