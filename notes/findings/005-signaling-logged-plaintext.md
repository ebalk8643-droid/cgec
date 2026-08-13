# 005 — V2 signaling payload logged in plaintext at INFO

## Component
`tgcalls/v2/InstanceV2Impl.cpp` — `processSignalingData`

## Impact
```cpp
RTC_LOG(LS_INFO) << "processSignalingData: " << std::string(data.begin(), data.end());
```

Decompressed signaling JSON (ICE `ufrag`/`pwd`, DTLS fingerprints, candidates, media state) may be written to client logs. If logs are shared (support, crash reports, debug builds), this leaks call-setup secrets useful for MitM on that call’s media path.

## Preconditions
- Logging enabled at INFO for this module
- Logs leave the device / are accessible to a third party

## Suggested fix
Remove the log or redact sensitive fields (`pwd`, fingerprints, full candidate lines).

## Severity guess
Low–medium depending on whether production builds ship this log line and whether logs are uploaded.

## Evidence
Static review of `InstanceV2Impl.cpp` (similar patterns may exist in Reference/Compat impls — verify when packaging a report).
