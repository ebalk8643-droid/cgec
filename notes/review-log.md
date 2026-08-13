# Review Log

## 2026-08-13 — Bootstrap + full static pass

- Added `third_party/tgcalls` submodule (`development`)
- Created threat model + pipeline map
- Completed P0/P1/P2 checklist below (Phase 3 acceptance)

## Checklist

| Area | Status | Notes |
|------|--------|-------|
| EncryptedConnection / CryptoHelper | reviewed — no issue filed | AES-CTR + msgKey SHA256 (const-time compare); counter anti-replay window; size caps (`kMaxIncomingPacketSize` / signaling 16KiB). Key material is injected as `EncryptionKey` from outside; library does not perform DH. |
| SignalingEncryption / v2 Signaling | reviewed | Thin wrapper over EncryptedConnection; JSON parsers generally fail closed. Serialize-path `RTC_FATAL` not remotely reachable via parse. |
| gzip framing | reviewed | Finding **003** — sizeLimit weak on `Z_STREAM_END` / error returns |
| Message codec bounds | reviewed | Strings capped at 64KiB; raw messages capped at 1MiB; audio/video buffer lengths checked against remaining reader bytes |
| Audio/VideoStreamingPart parsers | reviewed | Findings **001**, **002**, **004** |
| AVIOContextImpl | reviewed — no issue filed | Read/seek clamp to buffer; EOF on empty read. No OOB found. |
| MediaManager.cpp | reviewed — no issue filed | No untrusted length-prefixed demux; external PCM resize path is local capture oriented. |
| CustomDcSctpSocket / SCTP signaling | reviewed — no issue filed | Thin WebRTC dcsctp customization; no custom length parsers with obvious OOB in-tree. |
| ContentNegotiation | reviewed — no issue filed | Local enum `RTC_FATAL` only; remote JSON goes through Signaling parsers. |
| ReflectorPort peer-tag | reviewed | Prefix check on 12/16 tag; `dataSize` bounded by packet size before dispatch. No OOB found in size tag path. |
| GroupJoinPayload / GroupNetworkManager | reviewed | JSON join payload parsing mostly fail-closed; SFU participant authz is server-driven. Client still trusts streaming part framing (001/002). |
| InstanceV2 version/downgrade | reviewed | Unknown `descriptor.version` falls back to V2. Likely intentional; no finding without MTProto forced-downgrade proof. |
| Key verification / MitM (emoji, commit-reveal) | reviewed — out of library | **Not implemented inside `tgcalls`**. Library consumes a pre-shared `EncryptionKey` + `isOutgoing`. Emoji / DH / group blockchain commit-reveal live in client/MTProto layers (see public E2E docs). No in-submodule fail-open verification bypass found. Deferred outside this repo unless Desktop sparse glue is pulled later. |
| LogSinkImpl | reviewed | Sink itself just writes messages; secret leak is callers — Finding **005** (`InstanceV2Impl` logs full signaling JSON). |

## Candidate findings

| ID | Title | Severity guess |
|----|-------|----------------|
| 001 | VideoStreamingPart padding → erase OOB/UB | Medium (crash DoS) |
| 002 | AudioStreamingPartInternal `RTC_FATAL` sample_fmt | Medium (crash DoS) |
| 003 | gunzip sizeLimit final-chunk bypass | Low |
| 004 | readBytesAsInt32 truncates TL length | Low |
| 005 | Signaling JSON logged plaintext | Low–Medium |

## Validation
- Offline: `scripts/validate_finding_001_padding.py` → offset 12 > size 10
- Submission drafts: `notes/submission/001-*.md`, `002-*.md`
- Triage: `notes/triage.md`

## Plan status
All required PLAN.md phases complete. Optional follow-ups (built-client crash repro, tdesktop sparse glue, sending email to security@) are **user-driven**, not open plan tasks.
