# crosvm audit — session 1 (commit ea2b45e4c40ab836577b82795da6e6fe5f182fbd, 2026-08-13)

Goal: find a novel, guest→host, memory-corruption bug in a fresh/un-fuzzed crosvm surface.

## Method
- Deepened git history (11733 commits) → churn ranking of `devices/src/virtio`.
- Mapped un-fuzzed surfaces (no dedicated fuzz target): gpu, media/video, snd, net, scsi,
  vsock, wl, iommu, balloon, pmem, vhost-user protocol.
- Repo-wide sweep for real memory-corruption sinks: `slice::from_raw_parts(_mut)`, `Vec::set_len`,
  `copy_nonoverlapping`, `ptr.add/offset`, `get_unchecked`.
- Read/triaged each hot candidate; ran guest→host fuzzers (fs_server, p9) under ASan.

## Findings (all NEGATIVE for memory-corruption so far — crosvm Rust layer is well-hardened)

1. `virtqueue_fuzzer` immediate crash → **Rust panic** in `queue/split_queue.rs` `peek()`
   (`get_slice_at_addr(...).unwrap()` family). SIGABRT, not an ASan memory error.
   - Class: memory-SAFE panic → at most a guest-triggerable DoS of the device process; almost
     certainly already known to OSS-Fuzz (this target runs continuously). NOT escalated.

2. rutabaga 2D `transfer_2d()` (`rutabaga_gfx-0.1.80/src/rutabaga_2d.rs`): guest rect/stride/
   offset. **Safe** — rect bounds `checked_range!`, all offset math `checked_arithmetic!`, and
   the actual copies use `src.get(..)?` / `dst.get_mut(..)?` (OOB → `InvalidIovec` error, never
   an OOB access), `copy_from_slice` on equal-length subslices. No bug.

3. `video/{decoder,encoder}` `from_raw_parts(entries.as_ptr() as *const virtio_video_mem_entry,
   entries.len())`: **safe** — `entries` is `&[UnresolvedResourceEntry]`, a size-matched union;
   length stays in element units, so the reinterpret is size-preserving. No bug.

4. `GpuCommand::decode()` (`gpu/protocol.rs`): every arm is a bounds-checked `read_obj()?` over
   the guest `Reader` → returns `Err` on short input. **Safe**. (Variable-length processing like
   `nr_entries` happens later in `virtio_gpu.rs`, also via the bounded `Reader`.)

5. `common/data_model/flexible_array.rs` `set_len`: it's the FlexibleArray **trait** method
   (writes the struct `nents` field), NOT `Vec::set_len`; `get_valid_len()` clamps to the
   originally-allocated length. **Safe**.

## Systemic conclusion
crosvm's in-tree Rust systematically neutralizes the classic "guest count/length vs actual
buffer" OOB (the CVE-2026-53360 pattern) via bounded abstractions: `Reader`/`Writer`,
`slice::get()/get_mut()`, `checked_arithmetic!`/`checked_range!`, and `FlexibleArrayWrapper`
clamping. Memory-corruption is therefore concentrated in:
  (a) the **C dependencies** reachable via virtio-gpu 3D: `virglrenderer`, `gfxstream`
      (cf. CVE-2025-2509) — NOT in this repo (rutabaga_gfx is an external crate; virgl/gfxstream
      are external C libs). These are the real high-EV target but require building the C stack.
  (b) rare/subtle `unsafe` invariants (FFI lifetime, snapshot/restore deserialization).

## Fuzzing status (this session)
- fs_server_fuzzer (virtio-fs / FUSE, guest→host): ~90k exec/s, cov plateaued at 1111, 0 crashes.
- p9_tframe_fuzzer (9p, guest→host): ~52k exec/s, cov plateaued at 985, 0 crashes.
- Plateaued coverage ⇒ upstream OSS-Fuzz corpus already exhaustive for these; low marginal EV.

## Recommended next steps (higher EV; better on the 64 GB box)
- [ ] Build the C stack (`virglrenderer` + `gfxstream`) and write a **dedicated harness driving
      the guest→host 3D command stream** through rutabaga_gfx (feature `virgl_renderer`/`gfxstream`).
      This is where real memory-corruption historically lives and is in ChromeOS VRP scope.
- [ ] Write a Rutabaga2D-backed harness (pure Rust, no C dep) that processes full 2D command
      sequences (resource_create_2d → attach_backing → transfer_to_host_2d → set_scanout) to
      exercise cross-command state, not just per-command decode.
- [ ] Audit snapshot/restore deserialization paths (fresh churn) for state-confusion.
- [ ] Long (hours/days) coverage-guided campaigns with fresh corpora on the 64 GB box.
