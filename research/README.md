# VM / Hypervisor Vulnerability Research (crosvm — Track A)

Legitimate, defensive security research on public open-source code, targeting official
reward programs (ChromeOS VRP / Android AVF VRP) and responsible disclosure. All work is
local; no testing against third-party/production infrastructure.

## Target
- **crosvm** — Google's Rust VMM (ChromeOS Crostini, Android AVF, Cuttlefish).
- Canonical: https://chromium.googlesource.com/crosvm/crosvm (GitHub mirror: google/crosvm)
- Pinned commit under study: `ea2b45e4c40ab836577b82795da6e6fe5f182fbd` (2026-08-13)
- Boundary: malicious guest → host crosvm (sandboxed) process = VM/sandbox escape.

## Why crosvm (vs V8/core-KVM)
- Fresh, actively-churned code; less research-saturated than V8/core-KVM.
- Real memory-corruption lives in `unsafe` blocks + C deps (virglrenderer/gfxstream) reachable
  from the guest via virtio-gpu (cf. CVE-2025-2509).
- Locally buildable + fuzzable (cargo-fuzz + OSS-Fuzz targets); fully deterministic repro.
- In scope: ChromeOS VRP (guest→crosvm escape) and Android VRP (AVF).

## Repo layout
- `research/scripts/setup_env.sh` — reproducible toolchain + clone setup.
- `research/notes/progress.md` — running research log (triage, candidates, decisions).
- `research/fuzz_targets/` — new structure-aware fuzz targets we add to crosvm's `fuzz/`.
- `research/findings/` — confirmed candidates (PoC, minimized testcase, sanitizer evidence).

## Reward routes (verified 2026-08)
- ChromeOS VRP — guest→host sandbox escape / RCE in crosvm; up to ~$100k by severity.
- Android VRP (AVF) — crosvm as AVF VMM; dynamic model, high ceilings; pKVM boundary in scope.
- Upstream deps (virglrenderer/gfxstream): report upstream first, then Google VRP.
- Always: responsible disclosure (CVE + credit) regardless of cash route.
