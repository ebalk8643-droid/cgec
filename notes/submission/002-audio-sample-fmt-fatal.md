# Telegram Bug Bounty Report — Group call audio `RTC_FATAL` on unexpected sample format

**To:** security@telegram.org  
**Component:** Official `tgcalls` library — group call audio demux  
**Affected file:** `tgcalls/group/AudioStreamingPartInternal.cpp`  
**Function:** `AudioStreamingPartInternal::fillPcmBuffer`  
**Class:** Client crash / remote DoS

## Summary
After decoding an audio streaming part with FFmpeg, `fillPcmBuffer` converts only four sample formats (`AV_SAMPLE_FMT_S16`, `S16P`, `FLT`, `FLTP`). Any other `sample_fmt` hits `RTC_FATAL()`, which aborts the process. Untrusted group-call media should soft-fail, not terminate the app.

## Attack scenario
1. Attacker supplies a crafted audio container/streaming part that the victim decodes in a group call (via `AudioStreamingPart` / audio `VideoStreamingPart` content).
2. Decoder produces a frame with an unexpected `AVSampleFormat` (unusual codec path, planar/packed variant, or FFmpeg version skew).
3. Victim hits `RTC_FATAL` → process abort.

## Technical details
```cpp
switch (_frame->format) {
case AV_SAMPLE_FMT_S16: ...
case AV_SAMPLE_FMT_S16P: ...
case AV_SAMPLE_FMT_FLT: ...
case AV_SAMPLE_FMT_FLTP: ...
default: {
    RTC_FATAL() << "Unexpected sample_fmt";
} break;
}
```

Other error paths in the same function already do `_didReadToEnd = true; return;`.

### Related hardening
PCM buffer sizing uses unchecked `int` products (`nb_samples * channels`, `nb_samples * 2 * channels`) before `resize`/`memcpy`. Channels are capped at 8, which reduces risk, but checked `size_t` arithmetic would be safer.

## Suggested fix
```cpp
default: {
    RTC_LOG(LS_ERROR) << "Unexpected sample_fmt: " << _frame->format;
    _didReadToEnd = true;
    return;
}
```

Optionally whitelist codecs/formats before decode.

## Impact assessment
- Availability: remote crash during group-call audio handling
- Confidentiality/integrity: not directly broken
- Likely **app-level** severity; confirm `RTC_FATAL` behavior on release builds of Telegram Android/iOS/Desktop that ship this code path

## Notes
Identified by code review of public `tgcalls`. Happy to provide a crafted local container if useful for triage.
