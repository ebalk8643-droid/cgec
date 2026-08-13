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

## crash-c823dc0dcb3117f70c963125b1ea4821a3b942fe (virgl_fuzzer, session-4 seeded campaign)
- Found by the coverage-guided virgl_fuzzer campaign (cov ~939) after expanding the seed corpus.
- Input = seed-derived command sequence (DESTROY/CREATE blend + CLEAR).
- Replayed standalone with ASAN_OPTIONS=detect_leaks=0: EXIT=0, NO crash (only expected
  "Illegal command buffer" / GL "Unknown 1286" logs).
- Classification: non-reproducible (state-dependent across inputs in one process / OOM under the
  campaign's rss limit), NOT a memory-corruption bug. Retained for re-testing on the 64 GB box
  where a serious campaign + better triage (e.g., -runs with the file, rss tuning) is feasible.
