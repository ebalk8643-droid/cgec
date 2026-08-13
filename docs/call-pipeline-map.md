# Call Pipeline Map (`tgcalls`)

Upstream submodule: `third_party/tgcalls` (branch `development`).

## Protocol docs

- Bug bounty: https://core.telegram.org/bug-bounty
- Voice call E2E (legacy + pointers to newer): https://core.telegram.org/api/end-to-end/voice-calls
- Group call E2E: https://core.telegram.org/api/end-to-end/group-calls

## Stages → code

| Stage | Responsibility | Primary files |
|-------|----------------|---------------|
| Instance factory / version select | Pick V1 / V2 / Compat / Reference impl | `tgcalls/Instance.cpp`, `InstanceImpl.*`, `v2/InstanceV2*.*` |
| Encrypted packet crypto | Encrypt/decrypt signaling & media-related custom packets | `EncryptedConnection.*`, `CryptoHelper.*`, `v2/SignalingEncryption.*` |
| Signaling messages | Serialize/parse call control messages | `Message.*`, `v2/Signaling.*`, `v2/SignalingConnection.*`, `v2/ExternalSignalingConnection.*`, `v2/SignalingSctpConnection.*` |
| Compression | Optional gzip on signaling payloads | `utils/gzip.*` |
| Networking 1:1 | ICE/P2P, reflector UDP, direct networking | `NetworkManager.*`, `v2/ReflectorPort.*`, `v2/ReflectorRelayPortFactory.*`, `v2/NativeNetworkingImpl.*`, `v2/DirectNetworkingImpl.*`, `TurnCustomizerImpl.*` |
| Media pipeline | Capture/encode/send/receive | `MediaManager.*`, `ChannelManager.*`, `CodecSelectHelper.*`, platform capturers |
| Group calls | Multi-party join + forwarding consumer | `group/GroupInstanceCustomImpl.*`, `group/GroupInstanceReferenceImpl.*`, `group/GroupNetworkManager.*`, `group/GroupJoinPayload*.*` |
| Group streaming demux | Parse incoming audio/video streaming parts | `group/AudioStreamingPart*.*`, `group/VideoStreamingPart*.*`, `group/AVIOContextImpl.*`, `group/StreamingMediaContext.*` |
| SCTP / data channel | Reliable signaling channel pieces | `SctpDataChannelProviderInterfaceImpl.*`, `v2/CustomDcSctpSocket.*` |
| Content negotiation | Codec/content agreement | `v2/ContentNegotiation.*` |
| Local harness | In-process caller/callee tests | `tools/cli/` |

## Review queue

### P0
1. `EncryptedConnection` + `CryptoHelper` + `SignalingEncryption`
2. Length/framing parsers: `Message`, `v2/Signaling`, `utils/gzip`
3. Group streaming demux: `AudioStreamingPart*`, `VideoStreamingPart*`, `AVIOContextImpl`
4. Key verification / version downgrade paths in `InstanceV2*`

### P1
1. Reflector peer-tag / packet acceptance (`ReflectorPort*`)
2. Group join payload + network manager authz
3. Cross-impl interop (`InstanceV2CompatImpl` vs `InstanceV2Impl` vs Reference)

### P2
1. Log sinks / stats paths for secret leakage
2. Pure availability issues

## Version matrix (from upstream CLI docs)

| Version string | Implementation |
|----------------|----------------|
| 14.0.0 | `InstanceV2CompatImpl` |
| 13.0.0 (and several 7–12) | `InstanceV2Impl` |
| 11.0.0 / 10.0.0 | `InstanceV2ReferenceImpl` |
| 5.0.0 / 2.7.7 | legacy `InstanceImpl` |
