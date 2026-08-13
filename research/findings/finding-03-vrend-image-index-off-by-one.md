# Finding 03 — Off-by-one image index bound in vrend `translate_load` (incomplete `9f1ca944` fix)

> Status: STATIC finding, LOW severity (in-struct type-confused over-read + shift UB), but an
> unambiguous code defect: one of four sibling bound checks uses `>` instead of `>=`. It is a direct
> incompleteness of the recent hardening commit `9f1ca944 vrend/shader: check upper bounds of image
> and buffer index`.

## Target
- Project: **virglrenderer** (vrend GL renderer / TGSI→GLSL translator).
- File/func: `src/vrend/vrend_shader.c`, `translate_load()` (image path, ~line 3951).
- Commit: `7fcfce4…` (HEAD, 2026-08-13). Reachable via the GL path (virtio-gpu) used broadly on
  ChromeOS/Android — a crafted guest **TGSI shader**.

## Root cause / broken invariant
`PIPE_MAX_SHADER_IMAGES == 32`; `struct dump_ctx { ... struct vrend_shader_image images[32];
uint32_t images_used_mask; ... }` (valid image indices 0..31). In `translate_load`:
```c
if (sinfo->sreg_index < 0 || sinfo->sreg_index > PIPE_MAX_SHADER_IMAGES)  /* BUG: '>' allows 32 */
    return false;
if (!((1 << sinfo->sreg_index) & ctx->images_used_mask))   /* 1 << 32 => shift UB (uint32_t) */
    return false;
... ctx->images[sinfo->sreg_index].decl.Resource ...       /* images[32] => OOB-by-one */
... ctx->images[sinfo->sreg_index].decl.Format ...
```
`sinfo->sreg_index` derives from the guest TGSI instruction `Register.Index`. The check uses `>`
where the three sibling checks in the same file use `>=` (lines 3822 `dest_index >=
PIPE_MAX_SHADER_IMAGES`, 3882 `>= PIPE_MAX_SHADER_BUFFERS`, 4166 `>= PIPE_MAX_SHADER_IMAGES`). So
`sreg_index == 32` slips through, giving `1 << 32` (undefined for a 32-bit type; on x86 the shift
count is masked so it typically evaluates as `1 << 0 == 1`, i.e. `images_used_mask & 1`), and if
image 0 is declared the code proceeds to read `ctx->images[32]`.

## Security primitive / impact (honest)
- `ctx->images[32]` is one element past the 32-element array. Because `images_used_mask` (and more
  fields) immediately follow `images[]` in `struct dump_ctx`, this is an **in-struct, type-confused
  over-read** (interprets `images_used_mask`+following bytes as a `vrend_shader_image`), NOT a heap
  overflow past the allocation — so it is unlikely to be ASan-visible and is LOW severity. Effect:
  the mis-read `decl.Resource`/`decl.Format` steer GLSL type selection (wrong output / possible
  downstream error), guest→host. Plus the `1 << 32` shift is UB.
- Reachability: guest submits a TGSI shader whose IMAGE load uses register index 32 with image 0
  declared. (The three sibling sites correctly reject 32.)

## Novelty
- Unpatched at HEAD; introduced/left by `9f1ca944` which added this specific check with `>` while
  using `>=` elsewhere. Clean incompleteness of an accepted fix.

## Fix (see finding-03 patch): `>` → `>=`
```c
if (sinfo->sreg_index < 0 || sinfo->sreg_index >= PIPE_MAX_SHADER_IMAGES)
    return false;
```

## Disclosure route
Upstream to virglrenderer as a one-line follow-up to `9f1ca944` (fix + credit). Low severity, so
likely a normal (non-embargoed) MR. GL path is Google-relevant (ChromeOS/Android), but the
in-struct nature limits VRP value.
