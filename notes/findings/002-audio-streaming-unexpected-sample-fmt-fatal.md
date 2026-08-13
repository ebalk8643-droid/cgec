# 002 — AudioStreamingPartInternal: `RTC_FATAL` on unexpected PCM sample format

## Component
`tgcalls` group call audio demux — `third_party/tgcalls/tgcalls/group/AudioStreamingPartInternal.cpp`

## Affected symbols
- `AudioStreamingPartInternal::fillPcmBuffer`

## Impact
If FFmpeg decodes a crafted audio streaming part into a sample format other than `S16` / `S16P` / `FLT` / `FLTP`, the code hits:

```cpp
default: {
    RTC_FATAL() << "Unexpected sample_fmt";
} break;
```

`RTC_FATAL` aborts the process → remote crash/DoS of the Telegram client during group call media handling.

## Preconditions
- Attacker can cause the victim to decode a malicious audio container/part used by group calls (`AudioStreamingPart` / `VideoStreamingPart` audio content)
- Decoder yields a non-handled `AVSampleFormat` (or future format mismatch across FFmpeg versions)

## Root cause
Untrusted media decode path treats unexpected formats as a fatal programmer error instead of a soft failure (`_didReadToEnd = true` / skip part).

## Suggested fix
Replace `RTC_FATAL` with error log + `_didReadToEnd = true; return;` (same as other failure paths in this function). Optionally restrict accepted codecs/formats before decode.

## Related note (integer sizing)
Nearby PCM buffer sizing uses `nb_samples * channels` / `nb_samples * 2 * channels` as `int` without saturation. With `channels` capped at 8 this is harder to hit, but should use checked `size_t` math before `resize`/`memcpy`.

## Severity guess
App-level remote DoS via call media — similar band to finding 001 if confirmed on release builds (where `RTC_FATAL` is enabled).

## Evidence
Static code review of submodule sources. Runtime confirmation recommended in a local harness with a crafted container (do not target third parties).
