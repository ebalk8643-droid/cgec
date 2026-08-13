# 004 — `readBytesAsInt32` returns `uint8_t` (3-byte TL length truncated)

## Component
`VideoStreamingPart.cpp` — helper used by `readSerializedString` for Telegram-style long strings (`first byte == 254`, next 3 bytes = length)

## Impact
Declared return type is `absl::optional<uint8_t>`, so a 3-byte length is truncated to 8 bits. Long serialized strings (endpoint IDs ≥ 254 bytes, etc.) desynchronize parsing. Usually fails closed, but it is a latent protocol bug and interacts poorly with padding calculations.

## Root cause
```cpp
absl::optional<uint8_t> readBytesAsInt32(..., int count) {
    int32_t value = 0;
    memcpy(&value, data.data() + offset, count);
    ...
    return value; // truncates to uint8_t
}
```

## Suggested fix
Return `absl::optional<int32_t>` (or `uint32_t`), validate `0 <= length && offset + length + padding <= data.size()`.

## Severity guess
Low by itself; fix together with finding 001.

## Evidence
Static review of `VideoStreamingPart.cpp`.
