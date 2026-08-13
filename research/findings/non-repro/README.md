# Non-reproducible artifacts (NOT vulnerabilities)

Per the validation gate, an artifact is not a finding unless it reproduces locally on a
release-like build with a concrete sanitizer report. The items here do NOT qualify.

## crash-6faf792bec20f6823fdd83a61db6052a7a6232e4 (virgl_fuzzer)
- Found during a coverage-guided virgl_fuzzer campaign (crosvm/virglrenderer Track A).
- Input: mostly 0x53535353 dwords; first dword 0x53535300 => cmd=0, obj=0x53, len huge =>
  dispatcher rejects with "Illegal command buffer".
- Replayed standalone: EXIT=0, NO crash (only the expected "Illegal command buffer" logs).
- Classification: non-reproducible campaign artifact (likely OOM/timeout/cross-input GL state),
  NOT a memory-corruption bug. Retained only for re-testing on the 64 GB box.
