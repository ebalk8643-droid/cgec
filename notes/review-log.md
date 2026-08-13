# Review Log

## 2026-08-13 — Bootstrap + P0 review

- Added `third_party/tgcalls` submodule (`development`)
- Created threat model + pipeline map
- Reviewed crypto/framing/media parser hotspots

## Checklist

| Area | Status | Notes |
|------|--------|-------|
| EncryptedConnection / CryptoHelper | reviewed | AES-CTR + msgKey SHA256 check; counter window; size caps (`kMaxIncomingPacketSize`). No classic MAC bypass found. |
| SignalingEncryption / v2 Signaling | reviewed | Thin wrapper over EncryptedConnection; JSON parsers generally fail closed. Serialize-path `RTC_FATAL` not remotely reachable via parse. |
| gzip framing | reviewed | Finding **003** — sizeLimit weak on `Z_STREAM_END` / error returns |
| Message codec bounds | reviewed | Strings capped at 64KiB; raw messages capped at 1MiB; audio/video buffer lengths checked against remaining reader bytes |
| Audio/VideoStreamingPart parsers | reviewed | Findings **001**, **002**, **004** |
| ReflectorPort peer-tag | reviewed | Prefix check on 12/16 tag; `dataSize` bounded by packet size before dispatch. No OOB found in size tag path. |
| GroupJoinPayload / GroupNetworkManager | reviewed (pass 1) | JSON join payload parsing mostly fail-closed; no immediate overflow. Deeper SFU authz still open for pass 2. |
| InstanceV2 version/downgrade | reviewed | Unknown `descriptor.version` falls back to V2 (`InstanceV2Impl` / Reference). Likely intentional forward-compat; flag only if MTProto negotiation can force a weaker path unexpectedly. No separate finding yet. |
| LogSink secret leakage | reviewed | Finding **005** — plaintext signaling logged in `InstanceV2Impl` |

## Candidate findings

| ID | Title | Severity guess |
|----|-------|----------------|
| 001 | VideoStreamingPart padding → erase OOB/UB | Medium (crash DoS) |
| 002 | AudioStreamingPartInternal `RTC_FATAL` sample_fmt | Medium (crash DoS) |
| 003 | gunzip sizeLimit final-chunk bypass | Low |
| 004 | readBytesAsInt32 truncates TL length | Low |
| 005 | Signaling JSON logged plaintext | Low–Medium |

## Pass 2 notes
- Group join JSON parsing: fail-closed on missing transport fields; SFU authorization ultimately depends on server-side participant lists (client still trusts streaming part framing — see 001/002).
- Offline validator added: `scripts/validate_finding_001_padding.py` (confirms offset 12 > size 10 on crafted blob).

## Next / remaining
- Optional runtime crash confirmation of 001/002 inside a built client/harness
- Deeper E2E group-call blockchain / commit-reveal (mostly server+client outside this submodule)
- Draft bounty emails from findings 001–002 when ready to submit
