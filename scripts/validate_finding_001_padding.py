#!/usr/bin/env python3
"""Offline validator for finding 001 (VideoStreamingPart padding offset).

Simulates readSerializedString + consumeVideoStreamInfo offset arithmetic
on a crafted blob. Does not talk to Telegram network.
"""
from __future__ import annotations

import struct
import sys


def write_tl_string(payload: bytes) -> bytes:
    """Telegram-style padded string used by VideoStreamingPart."""
    if len(payload) < 254:
        out = bytes([len(payload)]) + payload
        pad = (-len(out)) % 4
        return out + b"\x00" * pad
    raise ValueError("use short strings for this demo")


def craft_missing_padding_blob() -> bytes:
    """Signature + container string whose padding bytes are truncated away."""
    sig = struct.pack("<I", 0xA12E810D)
    # length=5 ('hello') => header+payload = 6 bytes, needs 2 pad bytes to 8
    # We omit the 2 padding bytes so offset after padding exceeds buffer.
    container = bytes([5]) + b"hello"  # no padding
    # Stop here: consumeVideoStreamInfo will also read activeMask/events,
    # but the bug triggers as soon as offset += paddingBytes past EOF on
    # the container field alone when followed by truncated tail.
    # Build a *full* header with remaining fields present, but steal padding
    # from the end of the container field by overlapping next field incorrectly.
    #
    # Cleaner approach: provide exact bytes for container without padding,
    # then provide activeMask + eventCount so parser continues if it didn't
    # advance padding — but C++ *does* advance padding without checking.
    active_mask = struct.pack("<i", 1)
    event_count = struct.pack("<i", 1)
    # Minimal event: offset, endpoint string, rotation, extra
    event = struct.pack("<i", 0)
    event += write_tl_string(b"ep")
    event += struct.pack("<i", 0)
    event += struct.pack("<i", 0)
    # Intentionally truncated: only signature + unpadded container
    # When C++ adds paddingBytes=2, offset becomes len(sig)+6+2 which is
    # past the actual buffer if we don't include further bytes.
    return sig + container


def simulate_read_serialized_string(data: bytes, offset: int) -> tuple[str | None, int]:
    if offset >= len(data):
        return None, offset
    tmp = data[offset]
    offset += 1
    if tmp == 254:
        if offset + 3 > len(data):
            return None, offset
        length = int.from_bytes(data[offset : offset + 3], "little")
        # NOTE: upstream truncates to uint8 — mirror that bug
        length &= 0xFF
        offset += 3
        padding = (4 - (length % 4)) % 4
    else:
        length = tmp
        padding = (4 - ((length + 1) % 4)) % 4
    if offset + length > len(data):
        return None, offset
    result = data[offset : offset + length].decode("latin1")
    offset += length
    offset += padding  # BUG: not checked against len(data)
    return result, offset


def simulate_consume_video_stream_info(data: bytes) -> dict:
    offset = 0
    if offset + 4 > len(data):
        return {"ok": False, "reason": "short"}
    sig = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    if sig != 0xA12E810D:
        return {"ok": False, "reason": "bad signature"}
    container, offset = simulate_read_serialized_string(data, offset)
    if container is None:
        return {"ok": False, "reason": "container parse fail"}
    past_end = offset > len(data)
    return {
        "ok": True,
        "container": container,
        "offset": offset,
        "size": len(data),
        "offset_past_end": past_end,
        "would_erase_ub": past_end,
    }


def main() -> int:
    blob = craft_missing_padding_blob()
    result = simulate_consume_video_stream_info(blob)
    print("blob_hex:", blob.hex())
    print("result:", result)
    if result.get("would_erase_ub"):
        print("VALIDATION OK: offset exceeds size; C++ erase would be UB/crash")
        return 0
    print("VALIDATION UNEXPECTED: bug condition not hit")
    return 1


if __name__ == "__main__":
    sys.exit(main())
