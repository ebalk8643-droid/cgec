#!/usr/bin/env python3
"""Structure-aware TGSI shader corpus generator for virgl_fuzzer.

Byte-mutation (libFuzzer / OSS-Fuzz) can't synthesize valid TGSI text, so the vrend
shader translator (vrend_shader.c, 8.5k LoC — the richest bug surface) stays shallowly
covered. This generator emits many *valid, varied* TGSI shaders (different stages, temp/
const/input counts, instruction mixes, and — importantly — sampler/image/buffer register
indices near the array bounds, e.g. 30/31/32, to probe index-bound handling like
finding-03) and wraps each as a CREATE_OBJECT SHADER command buffer the fuzzer accepts.

Command format (see tests/testvirgl_encode.c + vrend_decode_create_shader):
  CMD0(CREATE_OBJECT, SHADER, len) | handle | type | offlen | num_tokens(=300) | so=0 | TGSI-text
  len = ceil(text_bytes/4) + 5 ; offlen = shader_len(bytes, incl NUL)

Usage: gen_tgsi_shaders.py OUT_DIR [COUNT]   (default COUNT=400)
"""
import os, struct, sys, random

CREATE_OBJECT = 1; OBJ_SHADER = 4
PIPE_SHADER_VERTEX = 0; PIPE_SHADER_FRAGMENT = 1; PIPE_SHADER_COMPUTE = 5

def le(x): return struct.pack("<I", x & 0xFFFFFFFF)
def cmd0(c, o, l): return c | (o << 8) | (l << 16)

def shader_cmd(handle, stype, tgsi_text):
    text = tgsi_text.encode() + b"\x00"
    sl = len(text); tdw = (sl + 3) // 4
    text_pad = text + b"\x00" * (tdw * 4 - sl)
    ln = tdw + 5
    return (le(cmd0(CREATE_OBJECT, OBJ_SHADER, ln)) + le(handle) + le(stype)
            + le(sl) + le(300) + le(0) + text_pad)

def rnd_swizzle(r):
    return "." + "".join(r.choice("xyzw") for _ in range(r.choice([1, 2, 3, 4])))

FLT_IMMS = ["{0.0000, 0.0000, 0.0000, 1.0000}", "{1.0000, 1.0000, 1.0000, 1.0000}",
            "{0x3f800000, 0x00000000, 0xbf800000, 0x40000000}", "{0.5000, 0.2500, 0.7500, 1.0000}"]
ALU3 = ["ADD", "MUL", "MAX", "MIN", "DP3", "DP4"]  # dst, s0, s1
ALU2 = ["MOV", "RCP", "FRC", "FLR", "ABS"]         # dst, s0

def gen_vertex(r):
    nin = r.randint(1, 4); ntmp = r.randint(1, 6); nconst = r.randint(0, 4)
    L = ["VERT"]
    for i in range(nin): L.append(f"DCL IN[{i}]")
    L.append("DCL OUT[0], POSITION")
    nout = r.randint(1, 3)
    for i in range(1, nout): L.append(f"DCL OUT[{i}], GENERIC[{i-1}]")
    L.append(f"DCL TEMP[0..{ntmp-1}]")
    if nconst: L.append(f"DCL CONST[0..{nconst-1}]")
    nimm = r.randint(1, 3)
    for i in range(nimm): L.append(f"IMM[{i}] FLT32 {r.choice(FLT_IMMS)}")
    # body
    body = []
    body.append(f"MOV TEMP[0], IN[0]")
    for _ in range(r.randint(2, 12)):
        op = r.choice(ALU2 + ALU3)
        d = f"TEMP[{r.randint(0,ntmp-1)}]"
        s0 = r.choice([f"IN[{r.randint(0,nin-1)}]", f"TEMP[{r.randint(0,ntmp-1)}]",
                       f"IMM[{r.randint(0,nimm-1)}]"] + ([f"CONST[{r.randint(0,nconst-1)}]"] if nconst else []))
        if op in ALU3:
            s1 = r.choice([f"TEMP[{r.randint(0,ntmp-1)}]", f"IMM[{r.randint(0,nimm-1)}]"])
            body.append(f"{op} {d}, {s0}, {s1}")
        else:
            body.append(f"{op} {d}, {s0}")
    body.append("MOV OUT[0], TEMP[0]")
    for i in range(1, nout): body.append(f"MOV OUT[{i}], TEMP[{r.randint(0,ntmp-1)}]")
    body.append("END")
    return "\n".join(L + body) + "\n"

def gen_fragment(r, with_sampler=False):
    L = ["FRAG"]
    nin = r.randint(1, 3)
    for i in range(nin): L.append(f"DCL IN[{i}], GENERIC[{i}], PERSPECTIVE")
    L.append("DCL OUT[0], COLOR")
    ntmp = r.randint(1, 6); L.append(f"DCL TEMP[0..{ntmp-1}]")
    nimm = r.randint(1, 3)
    for i in range(nimm): L.append(f"IMM[{i}] FLT32 {r.choice(FLT_IMMS)}")
    body = [f"MOV TEMP[0], IMM[0]"]
    if with_sampler:
        # probe sampler index near bounds (samplers[32])
        sidx = r.choice([0, 1, 15, 30, 31, 32])
        L.append(f"DCL SAMP[{sidx}]")
        L.append(f"DCL SVIEW[{sidx}], 2D, FLOAT")
        body.append(f"TEX TEMP[0], IN[0], SAMP[{sidx}], 2D")
    for _ in range(r.randint(2, 10)):
        op = r.choice(ALU2 + ALU3)
        d = f"TEMP[{r.randint(0,ntmp-1)}]"
        s0 = r.choice([f"IN[{r.randint(0,nin-1)}]", f"TEMP[{r.randint(0,ntmp-1)}]", f"IMM[{r.randint(0,nimm-1)}]"])
        if op in ALU3:
            s1 = r.choice([f"TEMP[{r.randint(0,ntmp-1)}]", f"IMM[{r.randint(0,nimm-1)}]"])
            body.append(f"{op} {d}, {s0}, {s1}")
        else:
            body.append(f"{op} {d}, {s0}")
    body.append("MOV OUT[0], TEMP[0]")
    body.append("END")
    return "\n".join(L + body) + "\n"

def gen_compute_image(r):
    # probe image index near bounds (images[32]) + LOAD/STORE (finding-03 region)
    iidx = r.choice([0, 1, 15, 30, 31, 32])
    L = ["COMP", "PROPERTY CS_FIXED_BLOCK_WIDTH 1", "PROPERTY CS_FIXED_BLOCK_HEIGHT 1",
         "PROPERTY CS_FIXED_BLOCK_DEPTH 1",
         f"DCL IMAGE[{iidx}], 2D, PIPE_FORMAT_R32_FLOAT, WR",
         "DCL SV[0], THREAD_ID", "DCL TEMP[0..1]"]
    body = ["MOV TEMP[0], SV[0]",
            f"LOAD TEMP[1], IMAGE[{iidx}], TEMP[0], 2D",
            f"STORE IMAGE[{iidx}], TEMP[0], TEMP[1], 2D",
            "END"]
    return "\n".join(L + body) + "\n"

def gen_compute_buffer(r):
    bidx = r.choice([0, 1, 15, 30, 31, 32])
    L = ["COMP", "PROPERTY CS_FIXED_BLOCK_WIDTH 1", "PROPERTY CS_FIXED_BLOCK_HEIGHT 1",
         "PROPERTY CS_FIXED_BLOCK_DEPTH 1",
         f"DCL BUFFER[{bidx}]", "DCL SV[0], THREAD_ID", "DCL TEMP[0..1]"]
    body = ["MOV TEMP[0], SV[0]",
            f"LOAD TEMP[1].x, BUFFER[{bidx}], TEMP[0].x",
            f"STORE BUFFER[{bidx}].x, TEMP[0].x, TEMP[1].x",
            "END"]
    return "\n".join(L + body) + "\n"

def main():
    out = sys.argv[1]; count = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    os.makedirs(out, exist_ok=True)
    r = random.Random(1337)
    n = 0
    for i in range(count):
        pick = r.random()
        if pick < 0.35:
            t, st = gen_vertex(r), PIPE_SHADER_VERTEX
        elif pick < 0.60:
            t, st = gen_fragment(r, with_sampler=False), PIPE_SHADER_FRAGMENT
        elif pick < 0.78:
            t, st = gen_fragment(r, with_sampler=True), PIPE_SHADER_FRAGMENT
        elif pick < 0.90:
            t, st = gen_compute_image(r), PIPE_SHADER_COMPUTE
        else:
            t, st = gen_compute_buffer(r), PIPE_SHADER_COMPUTE
        data = shader_cmd(1, st, t)
        with open(os.path.join(out, f"tgsi_{i:04d}"), "wb") as fh:
            fh.write(data)
        n += 1
    print(f"[*] wrote {n} TGSI shader seeds -> {out}")

if __name__ == "__main__":
    main()
