# Findings triage

Date: 2026-08-13  
Upstream: `third_party/tgcalls` @ submodule commit on branch `development`

| ID | Real? | Submit now? | Rationale |
|----|-------|-------------|-----------|
| 001 | Yes (logic/UB) | **Yes** | Clear missing bounds check; offline arithmetic validated; crash/DoS class |
| 002 | Yes (code path) | **Yes** (note reachability) | `RTC_FATAL` on untrusted decode path; needs format-reachability note |
| 003 | Yes (hardening) | Bundle / low | SizeLimit overshoot bounded; fix with 001/002 or alone as low |
| 004 | Yes (bug) | Bundle with 001 | Same file family; usually fail-closed; fix together |
| 005 | Conditional | Maybe | Depends whether shipping clients log INFO signaling; verify builds |

## Out of scope / deferred
- Unknown call-version → V2 fallback: likely intentional; no report without MTProto forced-downgrade proof
- Full WebRTC/FFmpeg upstream bugs unrelated to Telegram wrappers
- Production reflector load / third-party call interception

## Submission order
1. `notes/submission/001-videostreaming-padding-oob.md`
2. `notes/submission/002-audio-sample-fmt-fatal.md`
3. Optional follow-ups: 003–005
