# Finding 04 — NULL-pointer dereference in vrend `vrend_sync_shader_io` (guest→host DoS)

> Status: **RUNTIME-CONFIRMED**, 100% reproducible under AddressSanitizer (5/5 runs crash).
> This is the strongest finding: found by the structure-aware TGSI fuzzer, reproduces standalone
> on the ASan build with a concrete sanitizer report. Guest→host DoS of the host renderer process.

## Target
- Project: **virglrenderer** (vrend GL renderer), file `src/vrend/vrend_renderer.c`,
  function `vrend_sync_shader_io()` (line 4040).
- Commit: `7fcfce49616974dc7050fdbfb5bb915f4448d270` (HEAD, 2026-08-13).
- Reachable via the GL path (virtio-gpu) used broadly on ChromeOS/Android — a **guest-supplied
  TGSI shader** command stream. Boundary: untrusted guest → host virglrenderer/crosvm GPU process.

## How it was found
Structure-aware TGSI corpus (`research/scripts/gen_tgsi_shaders.py`) drove the vrend shader
translator far deeper than byte-mutation (coverage 512 → 1231 → **1577**). A 12-worker campaign on
the 64 GB box then mutated a seed's `DCL` into `LDC` (a valid opcode in an invalid position),
producing a malformed shader/command stream that reaches the crash.

## Reproduction
- Input: `finding-04/repro-crash.bin` (218 bytes) — fed directly to `virgl_fuzzer` (FuzzMode1).
- `ASAN_OPTIONS=detect_leaks=0 EGL_PLATFORM=surfaceless GALLIUM_DRIVER=llvmpipe \
   ./virgl_fuzzer repro-crash.bin` → **SEGV every run (5/5)**.
- ASan report:
```
AddressSanitizer: SEGV on unknown address 0x00000000015c
 #0 vrend_sync_shader_io   src/vrend/vrend_renderer.c:4040:74
 #1 vrend_fill_shader_key  src/vrend/vrend_renderer.c:4314
 #2 vrend_shader_select    src/vrend/vrend_renderer.c:4376
 #3 vrend_finish_shader    src/vrend/vrend_renderer.c:4444
 #4 vrend_shader_assign_tgsi src/vrend/vrend_renderer.c:4468
 #5 vrend_create_shader    src/vrend/vrend_renderer.c:4592
 #6 vrend_decode_create_shader src/vrend/vrend_decode.c:136
 #7 vrend_decode_create_object src/vrend/vrend_decode.c:864
 #8 vrend_decode_ctx_submit_cmd src/vrend/vrend_decode.c:2110
```

## Root cause / broken invariant
```c
struct vrend_shader_selector *prev =
    prev_type != PIPE_SHADER_INVALID ? sub_ctx->shaders[prev_type] : NULL;
if (prev) {                                   /* checks the SELECTOR is non-NULL ... */
   ...
   key->num_in_clip =
       sub_ctx->shaders[prev_type]->current->var_sinfo.num_out_clip;  /* ...but not ->current */
   key->num_in_cull =
       sub_ctx->shaders[prev_type]->current->var_sinfo.num_out_cull;
   ...
}
```
The `if (prev)` guard only verifies the previous-stage shader **selector** is non-NULL. It then
dereferences `prev->current` — the *currently-selected compiled variant* — which is `NULL` when the
previous-stage shader has been bound but has no successfully-compiled/selected variant (a malicious
guest can arrange this, e.g. by supplying malformed TGSI for the previous stage). `NULL->var_sinfo.
num_out_clip` faults at offset `0x15c`.

## Security primitive / impact
- Guest-triggerable **NULL-pointer dereference → SIGSEGV** in the host renderer. A malicious guest
  reliably crashes the host virglrenderer/crosvm GPU device process = **guest→host DoS** across the
  VM boundary. Not memory-corruption/RCE (fixed NULL+small offset, non-controllable) → DoS severity.
- 100% reliable; tiny (218-byte) trigger.

## Novelty
- Unpatched at HEAD `7fcfce4`. The `if (prev)` check guards the selector but not `->current`; the
  crash sits on the standard `create_shader → fill_shader_key → sync_shader_io` path. (Recommend an
  oss-sec / GitLab issue search before assigning a CVE, per Phase-9.)

## Fix (see finding-04/fix.patch)
Guard the `->current` dereference:
```c
if (sub_ctx->shaders[prev_type]->current) {
   key->num_in_clip = sub_ctx->shaders[prev_type]->current->var_sinfo.num_out_clip;
   key->num_in_cull = sub_ctx->shaders[prev_type]->current->var_sinfo.num_out_cull;
   if (vrend_state.use_gles && type == PIPE_SHADER_FRAGMENT)
      key->fs.available_color_in_bits =
          sub_ctx->shaders[prev_type]->current->var_sinfo.legacy_color_bits;
}
```

## Disclosure route
Upstream to virglrenderer (GitLab issue + MR with fix.patch) — this is a clean, reproducible
guest→host DoS on the GL path (ChromeOS/Android relevant). Strongest candidate for CVE + credit,
and the reproducible impact may qualify for ChromeOS VRP consideration (crosvm virtio-gpu uses this
renderer).
