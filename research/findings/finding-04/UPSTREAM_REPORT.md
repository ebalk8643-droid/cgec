# Upstream security report — virglrenderer (ready to submit)

Submit as a **confidential** issue at https://gitlab.freedesktop.org/virgl/virglrenderer/-/issues
(tick "This issue is confidential"), then optionally open an MR with the patch below. Attach
`repro-crash.bin` (or recreate it from the base64 at the bottom).

---

**Title:** NULL-pointer dereference in `vrend_sync_shader_io` — guest-triggerable host crash (guest→host DoS)

**Affected:** virglrenderer master @ `7fcfce49616974dc7050fdbfb5bb915f4448d270` (and earlier).

**Summary**

A malicious/buggy guest can crash the host renderer process (SIGSEGV) by submitting a crafted
virgl command stream that creates/selects a shader whose *previous pipeline stage* has a bound
shader selector without a compiled variant. `vrend_sync_shader_io()` checks that the previous-stage
**selector** is non-NULL but then dereferences its `->current` (the currently selected compiled
variant) without a NULL check.

**Crash (AddressSanitizer)**

```
AddressSanitizer: SEGV on unknown address 0x000000000000015c
 #0 vrend_sync_shader_io      src/vrend/vrend_renderer.c:4040:74
 #1 vrend_fill_shader_key     src/vrend/vrend_renderer.c:4314
 #2 vrend_shader_select       src/vrend/vrend_renderer.c:4376
 #3 vrend_finish_shader       src/vrend/vrend_renderer.c:4444
 #4 vrend_shader_assign_tgsi  src/vrend/vrend_renderer.c:4468
 #5 vrend_create_shader       src/vrend/vrend_renderer.c:4592
 #6 vrend_decode_create_shader src/vrend/vrend_decode.c:136
 #7 vrend_decode_create_object src/vrend/vrend_decode.c:864
 #8 vrend_decode_ctx_submit_cmd src/vrend/vrend_decode.c:2110
```

**Root cause** (`src/vrend/vrend_renderer.c`, `vrend_sync_shader_io`, ~line 4025-4041):

```c
struct vrend_shader_selector *prev =
    prev_type != PIPE_SHADER_INVALID ? sub_ctx->shaders[prev_type] : NULL;
if (prev) {                       /* selector checked non-NULL... */
   ...
   key->num_in_clip =
       sub_ctx->shaders[prev_type]->current->var_sinfo.num_out_clip;   /* ...but ->current is not */
   key->num_in_cull =
       sub_ctx->shaders[prev_type]->current->var_sinfo.num_out_cull;
   if (vrend_state.use_gles && type == PIPE_SHADER_FRAGMENT)
      key->fs.available_color_in_bits =
          sub_ctx->shaders[prev_type]->current->var_sinfo.legacy_color_bits;
}
```

`prev->current == NULL` when the previous-stage shader was bound but never had a variant
compiled/selected (reachable from the guest, e.g. via malformed TGSI for that stage). The
dereference then faults at offset `0x15c`.

**Impact:** guest → host DoS. A guest reliably crashes the host virglrenderer process (used by
crosvm/QEMU virtio-gpu). Not memory corruption (fixed NULL + small constant offset, not
attacker-controlled). 100% reproducible.

**Reproduction**

1. Build the in-tree libFuzzer target with ASan:
   `meson setup build -Dfuzzer=true -Dtests=true -Db_sanitize=address -Db_lundef=false \
     -Ddefault_library=static -Dc_args=-fsanitize=fuzzer-no-link -Dcpp_args=-fsanitize=fuzzer-no-link`
   `ninja -C build tests/fuzzer/virgl_fuzzer`
2. `EGL_PLATFORM=surfaceless LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe \
    ASAN_OPTIONS=detect_leaks=0 ./build/tests/fuzzer/virgl_fuzzer repro-crash.bin`
   → SEGV every run.

**Proposed fix** (guard the `->current` dereference):

```diff
       key->ssbo_binding_offset = prev->sinfo.ssbo_last_binding + 1;
       key->image_binding_offset = prev->sinfo.image_last_binding + 1;
 
-      key->num_in_clip = sub_ctx->shaders[prev_type]->current->var_sinfo.num_out_clip;
-      key->num_in_cull = sub_ctx->shaders[prev_type]->current->var_sinfo.num_out_cull;
-
-      if (vrend_state.use_gles && type == PIPE_SHADER_FRAGMENT)
-         key->fs.available_color_in_bits = sub_ctx->shaders[prev_type]->current->var_sinfo.legacy_color_bits;
+      /* A guest can bind a previous-stage shader with no compiled variant
+       * selected yet (->current == NULL); guard the dereference. */
+      if (sub_ctx->shaders[prev_type]->current) {
+         key->num_in_clip = sub_ctx->shaders[prev_type]->current->var_sinfo.num_out_clip;
+         key->num_in_cull = sub_ctx->shaders[prev_type]->current->var_sinfo.num_out_cull;
+
+         if (vrend_state.use_gles && type == PIPE_SHADER_FRAGMENT)
+            key->fs.available_color_in_bits = sub_ctx->shaders[prev_type]->current->var_sinfo.legacy_color_bits;
+      }
    }
```
(Verified: with this patch applied, the reproducer no longer crashes.)

**Reproducer (base64 of the 218-byte `virgl_fuzzer` input):**
```
AQQUAAEAAAAAAAAAOzgAAAAAAAAAAAAAVkVSVApEQ0wgSU5bMF0KTERDIE9VVFswXSwgUE9TSVRJT04KTU9WIE9VVFswXSwgSU5bMF0KRU5ECgAAHwACAAEAAAAAAAAAAQQdAAIAAAABAAAAXgAAACwBAAAAAAAARlJBRwpEQ0wgT1VUWzBdLCBDT0xPUgpJTU1bMF0gRkxUMzIgeyAxLjAwMDAAAAAAAD8AAMhCAADIQgAAAD8HAAgADwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
```
Recreate: `echo '<base64>' | base64 -d > repro-crash.bin`
