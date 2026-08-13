#!/usr/bin/env python3
"""Generate a seed corpus of valid virgl command buffers for virgl_fuzzer.

The fuzzer feeds its input directly to virgl_renderer_submit_cmd() as an array of
little-endian u32 dwords (see tests/fuzzer/virgl_fuzzer.c: FuzzMode1 pre-creates
resource handle 10, 200x200, then submits the input as the guest command buffer).

Command header: VIRGL_CMD0(cmd, obj, len) = cmd | (obj<<8) | (len<<16)
where `len` = number of payload dwords following the header.
Sizes/layouts taken from src/virgl_protocol.h.

Usage: gen_virgl_seeds.py [OUT_DIR]   (default: /tmp/virgl_corpus)
"""
import os, struct, sys

# command ids (enum virgl_context_cmd)
NOP=0; CREATE_OBJECT=1; SET_VIEWPORT_STATE=4; SET_FRAMEBUFFER_STATE=5
CLEAR=7; SET_STENCIL_REF=13; SET_BLEND_COLOR=14; SET_SCISSOR_STATE=15
SET_SAMPLE_MASK=0x18; SET_MIN_SAMPLES=0x2f  # informational; not all used

def hdr(cmd, obj, length):
    return cmd | (obj << 8) | (length << 16)

def pack(dwords):
    return b"".join(struct.pack("<I", d & 0xFFFFFFFF) for d in dwords)

def cmd(cmd_id, obj, payload):
    return pack([hdr(cmd_id, obj, len(payload))] + list(payload))

SEEDS = {}

# CLEAR (size 8): buffers, color[4], depth(double=2 dw), stencil
SEEDS["clear"] = cmd(CLEAR, 0, [0xF, 0,0,0,0, 0,0, 0])

# SET_VIEWPORT_STATE (1 viewport => 7 dw): start_slot + scale[3] + translate[3]
f = lambda x: struct.unpack("<I", struct.pack("<f", x))[0]
SEEDS["viewport"] = cmd(SET_VIEWPORT_STATE, 0,
                        [0, f(100.0),f(100.0),f(0.5), f(100.0),f(100.0),f(0.5)])

# SET_FRAMEBUFFER_STATE (nr_cbufs=0 => len 2): nr_cbufs, zsurf_handle
SEEDS["fb_state"] = cmd(SET_FRAMEBUFFER_STATE, 0, [0, 0])

# SET_STENCIL_REF (size 1)
SEEDS["stencil_ref"] = cmd(SET_STENCIL_REF, 0, [0])

# SET_BLEND_COLOR (4 floats)
SEEDS["blend_color"] = cmd(SET_BLEND_COLOR, 0, [f(1.0),f(1.0),f(1.0),f(1.0)])

# SET_SCISSOR_STATE (1 scissor => len 3): start_slot, minx_miny, maxx_maxy
SEEDS["scissor"] = cmd(SET_SCISSOR_STATE, 0, [0, 0, (200<<16)|200])

# NOP
SEEDS["nop"] = cmd(NOP, 0, [])

# --- CREATE_OBJECT / BIND_OBJECT (reach vrend_decode_create_* deeper) ---
CREATE_OBJECT = 1; BIND_OBJECT = 2
OBJ_BLEND = 1; OBJ_RASTERIZER = 2; OBJ_DSA = 3
# CREATE_OBJECT header carries object type in the `obj` field; payload[0]=handle.
# blend: VIRGL_OBJ_BLEND_SIZE = MAX_COLOR_BUFS(8)+3 = 11 dwords
SEEDS["create_blend"] = cmd(CREATE_OBJECT, OBJ_BLEND, [1] + [0]*10)
# dsa: VIRGL_OBJ_DSA_SIZE = 5
SEEDS["create_dsa"] = cmd(CREATE_OBJECT, OBJ_DSA, [2, 0, 0, 0, 0])
# rasterizer: handle + several state dwords (use 9 payload dwords, decoder validates length)
SEEDS["create_rasterizer"] = cmd(CREATE_OBJECT, OBJ_RASTERIZER, [3] + [0]*8)
# bind the created blend object (obj type in header, handle in payload)
SEEDS["bind_blend"] = cmd(BIND_OBJECT, OBJ_BLEND, [1])

# Combined pipeline-ish sequence to reach deeper state handling
SEEDS["seq_objects"] = (SEEDS["create_blend"] + SEEDS["bind_blend"]
                        + SEEDS["create_dsa"] + SEEDS["create_rasterizer"]
                        + SEEDS["fb_state"] + SEEDS["viewport"] + SEEDS["clear"])

# Combined realistic sequence: fb_state -> viewport -> scissor -> clear
SEEDS["seq_draw_setup"] = (SEEDS["fb_state"] + SEEDS["viewport"]
                           + SEEDS["scissor"] + SEEDS["clear"])

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/virgl_corpus"
    os.makedirs(out, exist_ok=True)
    for name, data in SEEDS.items():
        p = os.path.join(out, f"seed_{name}")
        with open(p, "wb") as fh:
            fh.write(data)
        print(f"wrote {p} ({len(data)} bytes)")
    print(f"[*] {len(SEEDS)} seeds -> {out}")

if __name__ == "__main__":
    main()
