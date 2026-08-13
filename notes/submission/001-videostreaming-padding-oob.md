# Telegram Bug Bounty Report — Group call VideoStreamingPart padding OOB

**To:** security@telegram.org  
**Component:** Official `tgcalls` library — group call media demux  
**Affected file:** `tgcalls/group/VideoStreamingPart.cpp`  
**Functions:** `readSerializedString`, `consumeVideoStreamInfo`  
**Class:** Client crash / remote DoS (memory-safety / undefined behavior)

## Summary
When parsing a group-call streaming part header, Telegram-style serialized strings compute TL padding and advance an `int offset` by `length + paddingBytes` **without verifying that padding bytes exist in the buffer**. `consumeVideoStreamInfo` then calls `data.erase(data.begin(), data.begin() + offset)`. If `offset > data.size()`, this is undefined behavior and typically crashes the client.

## Attack scenario
1. Attacker can cause a victim client to parse a crafted group-call streaming part (malicious participant / malicious media publisher path that feeds `VideoStreamingPart`).
2. Blob begins with signature `0xa12e810d` and a short serialized string whose payload fits in the remaining bytes but whose required 1–3 padding bytes are omitted.
3. Victim parses the part → offset past end → erase UB → crash (DoS of calls UI / process).

No need to break 1:1 E2E call crypto.

## Technical details
`readSerializedString` only checks `offset + length`:

```cpp
if (offset + length > data.size()) {
    return absl::nullopt;
}
std::string result(...);
offset += length;
offset += paddingBytes;  // unchecked
```

Later:

```cpp
data.erase(data.begin(), data.begin() + offset);
```

### Offline validation
A minimal truncated header (signature + unpadded 5-byte string `hello`) yields:
- buffer size = 10
- computed offset after padding = 12
- `offset > size` → erase would be invalid

Repro helper (local only): `scripts/validate_finding_001_padding.py` in the research workspace.

Example blob (hex): `0d812ea10568656c6c6f`

## Suggested fix
Before returning from `readSerializedString`:

```cpp
if (offset + length + paddingBytes > data.size()) {
    return absl::nullopt;
}
offset += length + paddingBytes;
```

Use `size_t` for offsets; assert `offset <= data.size()` before `erase`.

Related: helper `readBytesAsInt32` is declared to return `uint8_t`, truncating 3-byte TL lengths — should return `int32_t`/`uint32_t` and share the same bounds checks.

## Impact assessment
- Confidentiality: not directly broken
- Integrity: not a crypto break
- Availability: remote crash of official clients parsing group-call media parts
- Likely **app-level** severity under https://core.telegram.org/bug-bounty

## Notes
Static analysis against public `TelegramMessenger/tgcalls` `development` tree. Please advise if you need a crash capture on a specific shipping Telegram build/version.
