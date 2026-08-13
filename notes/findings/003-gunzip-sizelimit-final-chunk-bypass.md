# 003 — `gunzipData` sizeLimit not enforced on `Z_STREAM_END` path

## Component
`tgcalls/utils/gzip.cpp` — used by `InstanceV2Impl` / `InstanceV2ReferenceImpl` / `InstanceV2CompatImpl` when decompressing signaling (`sizeLimit = 2 * 1024 * 1024`)

## Impact
The advertised decompress cap can be exceeded by roughly one output resize quantum on the final successful inflate (`Z_STREAM_END`), because the limit is checked at loop entry but not after the finishing inflate. Secondary issues:
- Failed inflate paths may still `return output` (non-nullopt) with partial/garbage data
- Failed `inflateInit2` still returns an empty vector as “success”

Practical impact against 2 MiB limit is mostly **bounded overshoot / logic bug** (availability / robustness), not a classic heap overflow. Still worth fixing for defense-in-depth on peer-controlled signaling.

## Root cause
```cpp
while (status == Z_OK) {
    if (sizeLimit > 0 && stream.total_out > sizeLimit) {
        return absl::nullopt;
    }
    // inflate ...
}
if (inflateEnd(&stream) == Z_OK) {
    if (status == Z_STREAM_END) {
        output.resize(stream.total_out); // no sizeLimit check
    } else if (sizeLimit > 0 && output.size() > sizeLimit) {
        return absl::nullopt;
    }
}
return output; // even on init/inflate failure paths
```

## Suggested fix
- After inflate loop, require `status == Z_STREAM_END` and `total_out <= sizeLimit`, else `nullopt`
- Call `inflateEnd` in all paths; return `nullopt` on any error
- Cap `avail_out` so a single inflate cannot cross `sizeLimit`

## Severity guess
Low — hardening / DoS-adjacent. Report only bundled with stronger issues unless a larger bypass is demonstrated.

## Evidence
Static review + call sites in `v2/InstanceV2*.cpp` (`gunzipData(..., 2 * 1024 * 1024)`).
