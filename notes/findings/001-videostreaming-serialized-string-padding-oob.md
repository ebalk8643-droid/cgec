# 001 — VideoStreamingPart: serialized-string padding can advance offset past buffer (UB / crash)

## Component
`tgcalls` group call media demux — `third_party/tgcalls/tgcalls/group/VideoStreamingPart.cpp`

## Affected symbols
- `readSerializedString`
- `consumeVideoStreamInfo` → `data.erase(data.begin(), data.begin() + offset)`

## Impact
Crafted group-call video/audio streaming part header can make `offset` exceed `data.size()`. Subsequent `erase` with an end iterator past `end()` is undefined behavior and commonly crashes the client (remote DoS against call participants who parse the part).

Attacker model: malicious participant / malicious media publisher in a group call (or anyone who can supply a streaming part blob that victims parse). Does **not** require breaking E2E crypto of 1:1 calls.

## Preconditions
- Victim processes a `VideoStreamingPart` blob (audio or video content type)
- Blob starts with signature `0xa12e810d` and a Telegram-style serialized string whose **payload fits** but **padding bytes do not**

## Root cause
`readSerializedString` bounds-checks only `offset + length`, then unconditionally adds TL-style padding:

```cpp
if (offset + length > data.size()) {
    return absl::nullopt;
}
// ...
offset += length;
offset += paddingBytes;  // not checked against data.size()
```

`consumeVideoStreamInfo` then does:

```cpp
data.erase(data.begin(), data.begin() + offset);
```

If `offset > data.size()`, this is invalid.

### Minimal shape
1. Write signature `0xa12e810d`
2. Write a serialized string that consumes almost all remaining bytes (length OK) but requires 1–3 padding bytes that are **missing**
3. Deliver as group streaming part

## Suggested fix
After applying padding:

```cpp
if (offset < 0 || static_cast<size_t>(offset) > data.size()) {
    return absl::nullopt;
}
```

Also validate padding bytes are actually present before advancing (`offset + length + paddingBytes <= data.size()`), and prefer `size_t` for offsets.

## Severity guess
App-level crash/DoS in calls media path — likely mid-tier bounty if reproducible on shipping clients ($100–$10k range per Telegram’s app-level guidance). Protocol confidentiality not broken.

## Evidence
Static analysis of upstream `development` submodule at commit tracked in `.gitmodules` / `third_party/tgcalls`. No production exploit published here.
