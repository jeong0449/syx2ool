#!/usr/bin/env python3
"""
SyX2ool v0.1g — Korg X2/X3 SysEx & MIDI Toolkit

Subcommands
-----------
  import   Standard MIDI File -> X2/X3 ALL SEQUENCE DATA dump
  export   X2/X3 ALL SEQUENCE DATA dump -> SMF
  analyze  Inspect Songs, Tracks and User Patterns in a dump
  play     Play an SMF or an X2/X3 User Pattern through MIDI OUT
  send     Send SysEx with X2/X3-aware completion monitoring
  receive  Receive SysEx from MIDI IN and save it

Run:
  python syx2ool.py -h
  python syx2ool.py import -h
  python syx2ool.py export -h
  python syx2ool.py analyze -h
  python syx2ool.py play -h
  python syx2ool.py send -h
  python syx2ool.py receive -h

v0.1 notes
-----------
* Import is based on the hardware-tested SMF->X2 converter:
  Format 0, 96 PPQN, constant 4/4, constant tempo.
* Default import target is S9. --song may select S0..S9.
* Export accepts comma/range syntax such as 0,3,9 or 0-3,7,9.
* Song export produces SMF Format 1.
* Pattern export preserves X2/X3 note numbers; it does NOT remap drums to GM.
* Pattern Put expansion is not implemented yet. Unknown events are warned about.
"""

import argparse
import io
import time
import base64
import re
import struct
import sys
import zlib
import threading
import queue
import multiprocessing
from collections import defaultdict, deque
from pathlib import Path

try:
    import mido
except ImportError:
    mido = None

VERSION = "0.1g"
PPQN = 96
CONTROL_SIZE = 3702
SONG_CTL_SIZE = 296
SONG_ADDR_OFF = 3160
PATTERN_ADDR_OFF = 3500
PATTERN_END_OFF = 3700
SEQ_BASE_BLOCK = 4288

_EMPTY_SEQUENCE_ZLIB_B64 = "eNrtljtvE0EUhc88dr3ep4VBQjTZpIqoaOii2IpcUCGkiCYVkh3RhTJVtH+ZjpaZuev1PYlFRQVeKzseaf3l3k/3jPbnzYePnxAvY53PcsyKeVnVDdrOxQvOHVZrLWy6MK7L4g4YPt8/or/98fC97+HNchcubDarVzi7qq8xPAFblA7v4H38Tzug6y8GDGY17i6GIu5M3MQdBmtWNu7W3figkwcXaef3P4MPu+zwM2NWuebP9g9exl2BXQGc9cKfE7/U/Ir4NfEbzW+p/k76w9bYvVFkeTKKuklGyWcwOnoMq3zr7TIZxf1jMoq+T0ax2yWjH86uxCi2yago1fWRX0P1WfLrqH+v+8+o/5z4M80vzuMuGE38OfFL4leaXxO/IX6r+d04MlskpeEWhzQYRRzSYPSZz7DufR7+olEThzQYRRzSYBRxSIPRdRzSYNQ8iVEa0rE+9mt0fZb8OurfU/+Z7j8n/kzxszikweh5P4hRzS+JXxG/1vyG+C3Vf2RIg1FI7Ft07kXu7ZT7/ZQu77zEvofE3kNiv4HE/jqX2Jfg2I/1sV9D9Vnt11H/nvrPqP9c86fY47XEPox3ir0Zh3TPL4lfEb8mfqP5LdV/zCgk9jUk9s/m1B5yP35ZSOzvIbHvIbEPuZeD9C3H3mOM/VQf+TVUnyW/Tvfvqf+M+s+JL7G/+CKxx0Jin/hz4peaXxG/Jn5D/FbX30l/wSgk9g4S+xIS+5e5n85RUbuW2A+Q2D9AYh/P0WT0G/58kNox9lN9Rtdnya+j/r3uP6P+c+LPNP9GYt8vOPaJXxK/0vya+A3xW6qfhzR4lYMUEvvu5TnqpnN0khqMWon9LST2BhL7DST2cMPxg7QAH6R2jP1Un9V+HfXvqf9M958TXx2kpcQeNxL7FeaaXxK/In6t+Q3xW6r/6EF6en86vT+d3p/+m/enZXjvSR/I8s/tL8NtvVgvvsZb+LyX5bQ/7f/q/o0sv34DPh4NaQ=="
EMPTY_SEQUENCE_SYX = zlib.decompress(base64.b64decode(_EMPTY_SEQUENCE_ZLIB_B64))
assert len(EMPTY_SEQUENCE_SYX) == 4240

# Empirically captured S9 control block after GM System On on the X2.
# 296 bytes.  This makes the generated S9 GM-conformed without requiring
# a separate GM System On message before loading the sequence dump.
GM_SONG_CONTROL = bytes.fromhex(
    "000102030405060708090a0b0c0d0e0f03030303030303030303030303030303020202020202020202000202020202021346000000504859534943414c20200401136464646444443f12001f3c3e00fffd0000630a03001a0004040000006400000f227f007f01bf00006400000f227f007f01bf01006400000f227f007f01bf02006400000f227f007f01bf03006400000f227f007f01bf04006400000f227f007f01bf05006400000f227f007f01bf06006400000f227f007f01bf07006400000f227f007f01bf08806400001fa07f007f01bf09006400000f227f007f01bf0a006400000f227f007f01bf0b006400000f227f007f01bf0c006400000f227f007f01bf0d006400000f227f007f01bf0e006400000f227f007f01bf0f0404000000006301020000"
)
assert len(GM_SONG_CONTROL) == 296

# ---------- Korg packing / 48H container ----------

def unpack7(d):
    out = bytearray()
    i = 0
    while i < len(d):
        msb = d[i]
        i += 1
        for bit in range(7):
            if i >= len(d):
                break
            out.append(d[i] | (((msb >> bit) & 1) << 7))
            i += 1
    return bytes(out)


def pack7(d):
    out = bytearray()
    for i in range(0, len(d), 7):
        chunk = d[i:i+7]
        msb = 0
        low = bytearray()
        for bit, b in enumerate(chunk):
            if b & 0x80:
                msb |= 1 << bit
            low.append(b & 0x7F)
        out.append(msb)
        out.extend(low)
    return bytes(out)


def load_48h(path):
    b = Path(path).read_bytes()
    pos = -1
    for i in range(max(0, len(b) - 8)):
        if (b[i:i+2] == b"\xF0\x42" and (b[i+2] & 0xF0) == 0x30
                and b[i+3:i+6] == bytes((0x35, 0x48, 0x00))):
            pos = i
            break
    if pos < 0:
        raise ValueError("X2/X3 48H ALL SEQUENCE DATA DUMP not found")
    end = b.find(b"\xF7", pos)
    if end < 0:
        raise ValueError("SysEx terminator F7 not found")
    msg = b[pos:end+1]
    if len(msg) < 9:
        raise ValueError("48H message is too short")
    blocks = msg[6] | (msg[7] << 7)
    raw = unpack7(msg[8:-1])
    if len(raw) < CONTROL_SIZE:
        raise ValueError("unpacked payload is shorter than 3702-byte Control Data")
    ctl = bytearray(raw[:CONTROL_SIZE])
    seq = raw[CONTROL_SIZE:]
    if len(seq) != blocks * 16:
        raise ValueError(
            f"sequence size mismatch: header={blocks} blocks, payload={len(seq)//16} blocks"
        )
    return bytearray(msg[:6]), ctl, seq


def make_48h(header6, ctl, seq):
    if len(seq) % 16:
        raise ValueError("Sequence Data must be a multiple of 16 bytes")
    blocks = len(seq) // 16
    if blocks > 0x3FFF:
        raise ValueError("Sequence Data exceeds 14-bit block count")
    out = bytearray(header6)
    out += bytes((blocks & 0x7F, (blocks >> 7) & 0x7F))
    out += pack7(bytes(ctl) + bytes(seq))
    out.append(0xF7)
    return bytes(out)


# ---------- address / selection helpers ----------

def song_addresses(ctl, s):
    off = SONG_ADDR_OFF + s * 34
    return [int.from_bytes(ctl[off+2*i:off+2*i+2], "little") for i in range(17)]


def put_song_addresses(ctl, s, values):
    off = SONG_ADDR_OFF + s * 34
    for i, v in enumerate(values):
        ctl[off+2*i:off+2*i+2] = int(v).to_bytes(2, "little")


def pattern_address(ctl, p):
    off = PATTERN_ADDR_OFF + p * 2
    return int.from_bytes(ctl[off:off+2], "little")


def pattern_end(ctl):
    return int.from_bytes(ctl[PATTERN_END_OFF:PATTERN_END_OFF+2], "little")


def song_end_address(ctl, s):
    return song_addresses(ctl, s+1)[0] if s < 9 else pattern_address(ctl, 0)


def song_name(ctl, s):
    off = s * SONG_CTL_SIZE + 53
    raw = bytes(ctl[off:off+10])
    txt = "".join(chr(x) if 32 <= x < 127 else " " for x in raw).strip()
    return txt or f"S{s}"


def song_tempo(ctl, s):
    return int(ctl[s * SONG_CTL_SIZE + 49]) + 30


def song_channels(ctl, s):
    base = s * SONG_CTL_SIZE
    return [ctl[base+i] & 0x0F for i in range(16)]


def song_has_data(ctl, s):
    a = song_addresses(ctl, s)
    return any(a[t] < (a[t+1] if t < 15 else a[16]) for t in range(16))


def pattern_has_data(ctl, p):
    a = pattern_address(ctl, p)
    z = pattern_address(ctl, p+1) if p < 99 else pattern_end(ctl)
    return a < z


def parse_selector(text, lo, hi, label):
    """Parse N, N,M,K, N-M, or mixed forms such as 0-3,7,9."""
    if text is None:
        return []
    result = []
    seen = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"empty item in {label} selector")
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            raise ValueError(f"invalid {label} selector: {part!r}")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) is not None else a
        if a > b:
            raise ValueError(f"reversed {label} range: {part}")
        if a < lo or b > hi:
            raise ValueError(f"{label} must be in {lo}..{hi}: {part}")
        for n in range(a, b+1):
            if n not in seen:
                seen.add(n)
                result.append(n)
    return result


def seq_slice(seq, start_block, end_block):
    if end_block <= start_block:
        return b""
    a = (start_block - SEQ_BASE_BLOCK) * 16
    z = (end_block - SEQ_BASE_BLOCK) * 16
    if a < 0 or z < 0 or z > len(seq):
        raise ValueError(
            f"address outside Sequence Data: blocks {start_block}..{end_block}"
        )
    return bytes(seq[a:z])


# ---------- forward SMF -> X2 events ----------

def require_mido():
    if mido is None:
        raise RuntimeError("mido is required. Install it with: pip install mido")


def tt(t, base):
    if not 0 <= t <= 0x1FF:
        raise ValueError("event time out of range")
    return bytes((t & 255, base | ((t >> 8) & 1)))


def bar_ev(bar_no):
    return bytes((bar_no & 255, 0x60 | ((bar_no >> 8) & 3), 0, 0x13))


def end_ev(t, bar_no):
    return bytes((t & 255, 0x70 | ((t >> 8) & 1),
                  bar_no & 255, (bar_no >> 8) & 3))


def pc_ev(t, p):
    return tt(t, 0x30) + bytes((p & 127, 0x80))


def cc_ev(t, c, v):
    return tt(t, 0x40) + bytes((c & 127, v & 127))


def pb_ev(t, p):
    v = max(0, min(16383, p + 8192))
    return tt(t, 0x10) + bytes((v & 127, (v >> 7) & 127))


def note_ev(t, n, v, length):
    if not 1 <= v <= 127:
        raise ValueError(f"velocity out of range: {v}")
    kv = max(2, min(126, ((v + 1) // 2) * 2))
    return bytes((t & 255, 0x80 | kv | ((t >> 8) & 1),
                  length & 255, ((n & 127) << 1) | ((length >> 8) & 1)))


def read_midi_for_import(path):
    require_mido()
    m = mido.MidiFile(path)
    if m.type != 0 or len(m.tracks) != 1:
        raise ValueError("v0.1 import currently requires SMF Format 0")
    if m.ticks_per_beat != PPQN:
        raise ValueError("v0.1 import currently requires 96 PPQN")
    tick = 0
    ev = []
    tempos = []
    sig = []
    for order, msg in enumerate(m.tracks[0]):
        tick += msg.time
        if msg.is_meta:
            if msg.type == "set_tempo":
                tempos.append((tick, msg.tempo))
            elif msg.type == "time_signature":
                sig.append((tick, msg.numerator, msg.denominator))
        else:
            ev.append((tick, order, msg))
    if sig and any(t != 0 or n != 4 or d != 4 for t, n, d in sig):
        raise ValueError("v0.1 import requires constant 4/4")
    if len({x[1] for x in tempos}) > 1:
        raise ValueError("v0.1 import does not yet support tempo changes")
    return m, ev, tempos, tick


def midi_song_name(midpath):
    require_mido()
    m = mido.MidiFile(midpath)
    track_names, markers = [], []
    for tr in m.tracks:
        for msg in tr:
            if not msg.is_meta:
                continue
            if msg.type == "track_name" and msg.name.strip():
                track_names.append(msg.name.strip())
            elif msg.type == "marker" and msg.text.strip():
                markers.append(msg.text.strip())
    if track_names:
        title = track_names[0]
    elif markers:
        title = markers[0].split(";", 1)[0].strip()
    else:
        title = Path(midpath).stem
    return title


def x2_song_name_bytes(name):
    return name.upper().encode("ascii", "replace")[:10].ljust(10, b" ")


def make_x2_tracks(midpath):
    m, ev, tempos, endtick = read_midi_for_import(midpath)
    active = defaultdict(deque)
    notes, other = [], []
    for tick, order, msg in ev:
        if msg.type == "note_on" and msg.velocity:
            active[(msg.channel, msg.note)].append((tick, order, msg.velocity))
        elif msg.type in ("note_off", "note_on") and (
            msg.type == "note_off" or msg.velocity == 0
        ):
            q = active[(msg.channel, msg.note)]
            if q:
                st, so, vel = q.popleft()
                notes.append((msg.channel, st, tick, so, msg.note, vel))
        else:
            other.append((tick, order, msg))
    if any(active.values()):
        raise ValueError("unclosed notes in input MIDI")

    B = 384
    last = endtick // B
    et = endtick % B
    if et == 0 and endtick:
        last -= 1
        et = B
    per_ch = [[] for _ in range(16)]

    for tick, order, msg in other:
        if not hasattr(msg, "channel") or msg.channel >= 16:
            continue
        bar, t = divmod(tick, B)
        if msg.type == "program_change":
            data = pc_ev(t, msg.program)
        elif msg.type == "control_change":
            data = cc_ev(t, msg.control, msg.value)
        elif msg.type == "pitchwheel":
            data = pb_ev(t, msg.pitch)
        else:
            continue
        per_ch[msg.channel].append((bar, t, order, data))

    for ch, st, en, order, note, vel in notes:
        cur = st
        first = True
        while cur < en:
            bar = cur // B
            boundary = (bar + 1) * B
            stop = min(en, boundary)
            t = (cur - bar * B) if first else 0x1FE
            length = 0x1FE if en > boundary else stop - cur
            per_ch[ch].append(
                (bar, (cur - bar * B) if first else -1,
                 order, note_ev(t, note, vel, length))
            )
            cur = stop
            first = False

    tracks, counts = [], []
    for ch in range(16):
        grouped = defaultdict(list)
        for bar, t, order, data in per_ch[ch]:
            grouped[bar].append((t, order, data))
        raw = bytearray()
        count = 0
        for bar in range(last + 1):
            raw += bar_ev(bar)
            count += 1
            for _, _, data in sorted(grouped.get(bar, []), key=lambda x: (x[0], x[1])):
                raw += data
                count += 1
        raw += end_ev(et, last)
        count += 1
        while len(raw) % 16:
            raw.append(0)
        tracks.append(bytes(raw))
        counts.append(count)

    bpm = round(mido.tempo2bpm(tempos[0][1])) if tempos else 120
    return tracks, counts, last + 1, bpm


def import_song(args):
    # Empty template or an existing workspace.
    if args.template:
        header, ctl, seq = load_48h(args.template)
    else:
        tmp = Path(args.output).with_suffix(".embedded-empty.tmp")
        # Avoid writing the embedded image: parse it directly.
        p = EMPTY_SEQUENCE_SYX
        header = bytearray(p[:6])
        blocks = p[6] | (p[7] << 7)
        raw = unpack7(p[8:-1])
        ctl = bytearray(raw[:CONTROL_SIZE])
        seq = raw[CONTROL_SIZE:]
        if len(seq) != blocks * 16:
            raise ValueError("embedded empty dump size mismatch")

    s = args.song
    old_a = song_addresses(ctl, s)
    old_start = old_a[0]
    old_end = song_end_address(ctl, s)

    tracks, counts, bars, bpm = make_x2_tracks(args.input)

    # Build replacement Song Sequence Data: 16 tracks, empty tempo track.
    cur = old_start
    new_a = [cur]
    blob = bytearray()
    for tr in tracks:
        blob += tr
        cur += len(tr) // 16
        new_a.append(cur)
    new_end = cur

    prefix = seq_slice(seq, SEQ_BASE_BLOCK, old_start)
    suffix = seq_slice(seq, old_end, SEQ_BASE_BLOCK + len(seq)//16)
    newseq = prefix + bytes(blob) + suffix
    delta = new_end - old_end

    # GM-conformed Song control state captured on real X2. The 296-byte Song
    # control layout is slot-independent; then set tempo/name for the target.
    base = s * SONG_CTL_SIZE
    ctl[base:base+SONG_CTL_SIZE] = GM_SONG_CONTROL

    # The captured GM Song control template happened to contain Next Song = S0
    # (raw value 0x00).  Copying that value to S0 produced S0 -> S0 and
    # prevented normal playback on the real X2.  Real-hardware tests confirmed
    # that setting Next Song to OFF (0xFF) makes imported Songs work in S0 and
    # S1.  A fresh import therefore starts with Song chaining disabled.
    ctl[base+52] = 0xFF

    ctl[base+49] = max(0, min(210, bpm - 30))
    chosen = args.name if args.name is not None else midi_song_name(args.input)
    ctl[base+53:base+63] = x2_song_name_bytes(chosen)
    put_song_addresses(ctl, s, new_a)

    # Shift all later Song address tables and all Pattern addresses.
    for later in range(s + 1, 10):
        vals = [v + delta for v in song_addresses(ctl, later)]
        put_song_addresses(ctl, later, vals)

    for p in range(100):
        off = PATTERN_ADDR_OFF + 2*p
        v = int.from_bytes(ctl[off:off+2], "little")
        ctl[off:off+2] = (v + delta).to_bytes(2, "little")
    pe = pattern_end(ctl) + delta
    ctl[PATTERN_END_OFF:PATTERN_END_OFF+2] = pe.to_bytes(2, "little")

    out = make_48h(header, ctl, newseq)
    Path(args.output).write_bytes(out)

    print(f"SyX2ool {VERSION} import")
    print(f"  input       : {args.input}")
    print(f"  output      : {args.output}")
    print(f"  target      : S{s}")
    print(f"  song name   : {song_name(ctl, s)}")
    print(f"  tempo       : {bpm} BPM")
    print(f"  bars        : {bars}")
    print(f"  events      : {sum(counts)}")
    print(f"  seq blocks  : {len(newseq)//16}")
    print(f"  SysEx bytes : {len(out)}")


# ---------- reverse X2 events -> SMF ----------

def vlq(n):
    n = max(0, int(n))
    buf = [n & 0x7F]
    n >>= 7
    while n:
        buf.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(buf))


def meta(delta, typ, payload=b""):
    return vlq(delta) + bytes((0xFF, typ)) + vlq(len(payload)) + payload


def midi_event(delta, status, data):
    return vlq(delta) + bytes((status,)) + bytes(data)


def decode_x2_events(raw, midi_ch, context="track"):
    """
    Decode X2/X3 native 4-byte sequence events to MIDI events.

    v0.1b fixes tied notes that cross bar boundaries.

    v0.1e also preserves the native Track End position so exported Patterns
    retain their full measure length (important for seamless looping).  The X2 forward
    converter represents such a note as one or more segments:

      first segment:        normal event time, length = 0x1FE
      continuation segment: event time = 0x1FE, length = 0x1FE or final length

    A continuation is not a new Note On.  Keep the original note open and
    emit one Note Off only when the final segment supplies a real length.
    """
    events = []
    warnings = []
    current_bar = 0
    tied = defaultdict(list)  # note -> FIFO of open cross-bar note instances
    end_tick = None

    for off in range(0, len(raw) - 3, 4):
        b0, b1, b2, b3 = raw[off:off+4]
        if (b0, b1, b2, b3) == (0, 0, 0, 0):
            continue

        # Note event: DATA(1-H) = 1vvv vvvt.
        # Must be tested before event-type nibbles because b1 may be F0..FE.
        if b1 & 0x80:
            t = b0 | ((b1 & 1) << 8)
            vel = b1 & 0x7E
            length = b2 | ((b3 & 1) << 8)
            note = (b3 >> 1) & 0x7F
            bar_tick = current_bar * 384

            if t == 0x1FE:
                # Continuation of a note begun in an earlier bar.
                if not tied[note]:
                    warnings.append(
                        f"{context} +0x{off:04X}: orphan tied-note continuation "
                        f"for note {note}"
                    )
                    # Best-effort recovery: start it at the bar boundary.
                    events.append((bar_tick, 20, 0x90 | midi_ch, (note, vel)))
                    tied[note].append(True)

                # Continuations for repeated/overlapping notes of the same pitch
                # occur in FIFO order in the native stream.
                tied[note].pop(0)
                if length == 0x1FE:
                    tied[note].append(True)
                else:
                    events.append((bar_tick + length, 10,
                                   0x80 | midi_ch, (note, 0)))
                if not tied[note]:
                    tied.pop(note, None)
                continue

            tick = bar_tick + t
            events.append((tick, 20, 0x90 | midi_ch, (note, vel)))

            if length == 0x1FE:
                tied[note].append(True)
            else:
                events.append((tick + length, 10,
                               0x80 | midi_ch, (note, 0)))
            continue

        typ = b1 & 0xF0

        # BAR stores bar number, not event time.
        if typ == 0x60:
            current_bar = b0 | ((b1 & 0x03) << 8)
            continue

        # Track End stores both time-within-bar and bar number.  Preserve
        # its absolute position even when the last musical event occurs earlier.
        if typ == 0x70:
            end_t = b0 | ((b1 & 0x01) << 8)
            end_bar = b2 | ((b3 & 0x03) << 8)
            end_tick = end_bar * 384 + end_t
            continue

        t = b0 | ((b1 & 1) << 8)
        tick = current_bar * 384 + t

        if typ == 0x10:  # Pitch Bend
            events.append((tick, 30, 0xE0 | midi_ch, (b2 & 0x7F, b3 & 0x7F)))
        elif typ == 0x20:  # Channel Aftertouch
            events.append((tick, 30, 0xD0 | midi_ch, (b2 & 0x7F,)))
        elif typ == 0x30:  # Program Change
            events.append((tick, 30, 0xC0 | midi_ch, (b2 & 0x7F,)))
        elif typ == 0x40:  # Control Change
            events.append((tick, 30, 0xB0 | midi_ch, (b2 & 0x7F, b3 & 0x7F)))
        elif typ == 0x50:  # Polyphonic Key Pressure
            events.append((tick, 30, 0xA0 | midi_ch, (b2 & 0x7F, b3 & 0x7F)))
        else:
            warnings.append(
                f"{context} +0x{off:04X}: unsupported event "
                f"{b0:02X} {b1:02X} {b2:02X} {b3:02X}"
            )

    if tied:
        warnings.append(
            f"{context}: unterminated tied note(s): " +
            ", ".join(
                f"{n}x{len(tied[n])}" for n in sorted(tied)
            )
        )

    return events, warnings, end_tick


def build_midi_track(events, name, end_tick=None):
    out = bytearray()
    out += meta(0, 0x03, name.encode("ascii", "replace")[:127])
    prev = 0
    for tick, priority, status, data in sorted(events, key=lambda x: (x[0], x[1])):
        if tick < prev:
            tick = prev
        out += midi_event(tick - prev, status, data)
        prev = tick
    # Keep the native Track End position.  This matters for User Patterns:
    # without the trailing silence, a loop can restart too early (rush).
    final_tick = prev if end_tick is None else max(prev, end_tick)
    out += meta(final_tick - prev, 0x2F)
    return bytes(out)


def conductor_track(name, bpm):
    out = bytearray()
    out += meta(0, 0x03, name.encode("ascii", "replace")[:127])
    usec = round(60_000_000 / max(1, bpm))
    out += meta(0, 0x51, usec.to_bytes(3, "big"))
    out += meta(0, 0x58, bytes((4, 2, 24, 8)))
    out += meta(0, 0x2F)
    return bytes(out)


def make_smf(tracks):
    hdr = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), PPQN)
    out = bytearray(hdr)
    for tr in tracks:
        out += b"MTrk" + struct.pack(">I", len(tr)) + tr
    return bytes(out)


def export_song(ctl, seq, s):
    a = song_addresses(ctl, s)
    chs = song_channels(ctl, s)
    name = song_name(ctl, s)
    bpm = song_tempo(ctl, s)
    tracks = [conductor_track(name, bpm)]
    warnings = []
    for t in range(16):
        z = a[t+1] if t < 15 else a[16]
        raw = seq_slice(seq, a[t], z)
        ev, w, end_tick = decode_x2_events(raw, chs[t], f"S{s} T{t+1}")
        warnings.extend(w)
        tracks.append(build_midi_track(ev, f"T{t+1:02d}", end_tick))
    return make_smf(tracks), warnings


def export_pattern(ctl, seq, p):
    a = pattern_address(ctl, p)
    z = pattern_address(ctl, p+1) if p < 99 else pattern_end(ctl)
    raw = seq_slice(seq, a, z)
    # Pattern itself has no complete Song/Track context. Preserve note numbers
    # and wrap the events in a simple 96-PPQN SMF on MIDI channel 1 (index 0).
    ev, warnings, end_tick = decode_x2_events(raw, 0, f"P{p:02d}")
    tracks = [
        conductor_track(f"P{p:02d}", 120),
        build_midi_track(ev, f"P{p:02d} raw", end_tick)
    ]
    return make_smf(tracks), warnings


def safe_filename(s):
    s = "".join(c if c.isalnum() or c in "-_ " else "_" for c in s).strip()
    return (s or "Song").replace(" ", "_")


def export_cmd(args):
    _, ctl, seq = load_48h(args.input)

    songs = set()
    patterns = set()

    if args.song:
        songs.update(parse_selector(args.song, 0, 9, "song"))
    if args.pattern:
        patterns.update(parse_selector(args.pattern, 0, 99, "pattern"))
    if args.songs or args.all:
        songs.update(s for s in range(10) if song_has_data(ctl, s))
    if args.patterns or args.all:
        patterns.update(p for p in range(100) if pattern_has_data(ctl, p))

    if not songs and not patterns:
        raise ValueError(
            "no export target selected; use --song, --songs, --pattern, --patterns, or --all"
        )

    outdir = Path(args.output_dir) if args.output_dir else Path(args.input).with_name(
        Path(args.input).stem + "_export"
    )
    outdir.mkdir(parents=True, exist_ok=True)

    total_warnings = 0
    for s in sorted(songs):
        if not song_has_data(ctl, s):
            print(f"warning: S{s} has no recorded track data", file=sys.stderr)
        smf, warnings = export_song(ctl, seq, s)
        fn = outdir / f"S{s}_{safe_filename(song_name(ctl, s))}.mid"
        fn.write_bytes(smf)
        print(f"S{s} -> {fn.name}")
        total_warnings += len(warnings)
        if warnings and not args.quiet:
            for w in warnings[:10]:
                print("  warning:", w, file=sys.stderr)
            if len(warnings) > 10:
                print(f"  warning: ... {len(warnings)-10} more", file=sys.stderr)

    for p in sorted(patterns):
        if not pattern_has_data(ctl, p):
            print(f"warning: P{p:02d} is empty; skipped", file=sys.stderr)
            continue
        smf, warnings = export_pattern(ctl, seq, p)
        fn = outdir / f"P{p:02d}.mid"
        fn.write_bytes(smf)
        print(f"P{p:02d} -> {fn.name}  [raw X2 note map; no GM drum remap]")
        total_warnings += len(warnings)
        if warnings and not args.quiet:
            for w in warnings[:10]:
                print("  warning:", w, file=sys.stderr)
            if len(warnings) > 10:
                print(f"  warning: ... {len(warnings)-10} more", file=sys.stderr)

    if total_warnings:
        print(f"Completed with {total_warnings} unsupported/unknown event warning(s).")


# ---------- analyze ----------

def analyze_cmd(args):
    msg_header, ctl, seq = load_48h(args.input)
    print(f"SyX2ool {VERSION} analyze")
    print(f"File          : {args.input}")
    print(f"Control Data  : {len(ctl)} bytes")
    print(f"Sequence Data : {len(seq)} bytes ({len(seq)//16} blocks)")
    print()
    print("Songs")
    print("-----")
    for s in range(10):
        a = song_addresses(ctl, s)
        used = song_has_data(ctl, s)
        nonempty_tracks = []
        for t in range(16):
            z = a[t+1] if t < 15 else a[16]
            if a[t] < z:
                nonempty_tracks.append(str(t+1))
        tr = ",".join(nonempty_tracks) if nonempty_tracks else "-"
        print(
            f"S{s}  {'DATA ' if used else 'empty'}  "
            f"{song_tempo(ctl,s):3d} BPM  "
            f"name={song_name(ctl,s)!r}  tracks={tr}  "
            f"T1={a[0]} Tempo={a[16]}"
        )

    used_patterns = [p for p in range(100) if pattern_has_data(ctl, p)]
    print()
    print("Patterns")
    print("--------")
    print(f"Used: {len(used_patterns)} / 100")
    if used_patterns:
        line = []
        for p in used_patterns:
            a = pattern_address(ctl, p)
            z = pattern_address(ctl, p+1) if p < 99 else pattern_end(ctl)
            line.append(f"P{p:02d}({z-a} blk)")
        print(" ".join(line))
    print(f"Pattern End: {pattern_end(ctl)}")



# ---------- MIDI playback ----------

def _open_midi_output(spec):
    if mido is None:
        raise RuntimeError("mido is required for playback; install with: py -m pip install mido python-rtmidi")
    names = mido.get_output_names()
    if not names:
        raise RuntimeError("no MIDI OUT ports found")
    if spec is None:
        if len(names) == 1:
            name = names[0]
        else:
            listing = "\\n".join(f"  {i}: {n}" for i, n in enumerate(names))
            raise ValueError("multiple MIDI OUT ports found; choose one with --port:\\n" + listing)
    else:
        try:
            idx = int(spec)
        except ValueError:
            matches = [n for n in names if spec.lower() in n.lower()]
            if len(matches) != 1:
                raise ValueError(f"MIDI OUT port '{spec}' did not match exactly one port")
            name = matches[0]
        else:
            if idx < 0 or idx >= len(names):
                raise ValueError(f"MIDI OUT port index out of range: {idx}")
            name = names[idx]
    return name, mido.open_output(name)


def _midi_for_play(args):
    path = Path(args.input)
    if path.suffix.lower() in (".syx", ".sys"):
        if args.pattern is None:
            raise ValueError("a SysEx input requires --pattern N")
        if not 0 <= args.pattern <= 99:
            raise ValueError("pattern must be 0..99")
        _, ctl, seq = load_48h(path)
        if not pattern_has_data(ctl, args.pattern):
            raise ValueError(f"P{args.pattern:02d} is empty")
        smf, warnings = export_pattern(ctl, seq, args.pattern)
        if warnings:
            print(f"warning: {len(warnings)} unsupported/unknown Pattern event(s)", file=sys.stderr)
        return mido.MidiFile(file=io.BytesIO(smf)), f"P{args.pattern:02d} from {path.name}"
    if args.pattern is not None:
        raise ValueError("--pattern is only used with an X2/X3 .syx input")
    return mido.MidiFile(str(path)), path.name


def _build_play_schedule(mid, bpm=None, channel=None):
    """Return (scheduled_messages, duration_seconds).

    scheduled_messages is a list of (seconds_from_start, message).  Meta events
    are used for timing/tempo but are not sent.  The final duration includes
    trailing delta time up to End-of-Track, which is important for patterns.
    """
    tempo = mido.bpm2tempo(bpm) if bpm is not None else 500000
    merged = mido.merge_tracks(mid.tracks)
    elapsed = 0.0
    scheduled = []
    for msg in merged:
        if msg.time:
            elapsed += mido.tick2second(msg.time, mid.ticks_per_beat, tempo)
        if msg.is_meta:
            if msg.type == "set_tempo" and bpm is None:
                tempo = msg.tempo
            continue
        out = msg
        if channel is not None and hasattr(msg, "channel"):
            out = msg.copy(channel=channel - 1)
        scheduled.append((elapsed, out))
    return scheduled, elapsed


def _sleep_until(deadline):
    """Sleep against an absolute perf_counter deadline."""
    while True:
        remain = deadline - time.perf_counter()
        if remain <= 0:
            return
        # Leave a small final interval to the OS scheduler instead of chaining
        # relative sleeps from the previous MIDI event.
        time.sleep(remain if remain < 0.003 else remain - 0.001)


def _play_schedule_once(schedule, port, origin, loop_index=0):
    for offset, msg in schedule:
        _sleep_until(origin + offset)
        port.send(msg)


def _timing_line(loop_index, expected, actual):
    err_ms = (actual - expected) * 1000.0
    print(f"timing loop {loop_index + 1:4d}: expected={expected:.6f}  actual={actual:.6f}  error={err_ms:+.3f} ms")

def ports_cmd(args):
    if mido is None:
        raise RuntimeError("mido is required to list MIDI ports; install with: py -m pip install mido python-rtmidi")
    out_names = mido.get_output_names()
    in_names = mido.get_input_names()
    print("MIDI OUT ports")
    print("--------------")
    if out_names:
        for i, name in enumerate(out_names):
            print(f"{i}: {name}")
    else:
        print("(none)")
    print("\nMIDI IN ports")
    print("-------------")
    if in_names:
        for i, name in enumerate(in_names):
            print(f"{i}: {name}")
    else:
        print("(none)")



def _seconds_at_tick(mid, target_tick, bpm=None):
    """Return elapsed seconds at target_tick, respecting the SMF tempo map."""
    if bpm is not None:
        return mido.tick2second(
            target_tick, mid.ticks_per_beat, mido.bpm2tempo(bpm)
        )

    tempo = mido.bpm2tempo(120)
    elapsed = 0.0
    pos = 0
    for msg in mido.merge_tracks(mid.tracks):
        next_pos = pos + msg.time
        if target_tick <= next_pos:
            elapsed += mido.tick2second(
                target_tick - pos, mid.ticks_per_beat, tempo
            )
            return elapsed
        elapsed += mido.tick2second(msg.time, mid.ticks_per_beat, tempo)
        pos = next_pos
        if msg.is_meta and msg.type == "set_tempo":
            tempo = msg.tempo

    if target_tick > pos:
        elapsed += mido.tick2second(
            target_tick - pos, mid.ticks_per_beat, tempo
        )
    return elapsed

def play_cmd(args):
    if mido is None:
        raise RuntimeError("mido is required for playback; install with: py -m pip install mido python-rtmidi")
    if args.list_ports:
        names = mido.get_output_names()
        if not names:
            print("No MIDI OUT ports found.")
        else:
            for i, name in enumerate(names):
                print(f"{i}: {name}")
        return
    if not args.input:
        raise ValueError("input file is required unless --list-ports is used")
    if args.bpm is not None and args.bpm <= 0:
        raise ValueError("BPM must be greater than zero")
    mid, label = _midi_for_play(args)
    name, port = _open_midi_output(args.port)
    print(f"MIDI OUT: {name}")
    print(f"Playing: {label}" + (f"  BPM={args.bpm:g}" if args.bpm else "") +
          (f"  CH={args.channel}" if args.channel else ""))
    if args.loop:
        print("Loop: ON  (Ctrl+C to stop)")
    schedule, event_duration = _build_play_schedule(mid, args.bpm, args.channel)

    # Loop boundaries are musical measure boundaries, not the time of the
    # last MIDI message.  The complete SMF length includes trailing delta time
    # before End-of-Track.  For --bpm, convert that full tick span at the
    # requested tempo.
    merged = mido.merge_tracks(mid.tracks)
    last_tick = sum(msg.time for msg in merged)
    if last_tick <= 0:
        raise ValueError("MIDI duration is zero")

    # Pattern looping must end on a musical bar boundary, not at the last
    # sounding event. Read the initial time signature (default 4/4), compute
    # ticks per bar, then round the occupied span up to the next full bar.
    numerator, denominator = 4, 4
    for tr in mid.tracks:
        abs_tick = 0
        for msg in tr:
            abs_tick += msg.time
            if msg.is_meta and msg.type == "time_signature" and abs_tick == 0:
                numerator, denominator = msg.numerator, msg.denominator
                break

    ticks_per_bar = mid.ticks_per_beat * numerator * 4 / denominator
    bars = max(1, int((last_tick + ticks_per_bar - 1) // ticks_per_bar))
    duration_ticks = int(round(bars * ticks_per_bar))

    # For looping, the next downbeat is anchored to the complete musical
    # bar boundary.  Without --bpm, respect the file's tempo map all the way
    # to that boundary.  For one-shot playback, no artificial wait is needed.
    if args.loop:
        duration = _seconds_at_tick(mid, duration_ticks, args.bpm)
    else:
        duration = event_duration

    if args.timing_log:
        beats = duration_ticks / mid.ticks_per_beat
        print(
            f"Scheduler: absolute perf_counter  duration={duration:.6f} s  "
            f"last_tick={last_tick}  loop_ticks={duration_ticks}  "
            f"bars={bars}  time={numerator}/{denominator}  beats={beats:g}"
        )
    # One origin for the whole run.  Loop N always starts at origin + N*duration;
    # a previous loop cannot move the next downbeat earlier or later.
    origin = time.perf_counter() + 0.050
    loop_index = 0
    try:
        while True:
            expected = origin + loop_index * duration
            _sleep_until(expected)
            actual = time.perf_counter()
            if args.timing_log:
                _timing_line(loop_index, expected, actual)
            _play_schedule_once(schedule, port, expected, loop_index)
            loop_index += 1
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("\\nStopped.")
    finally:
        try:
            port.panic()
        except Exception:
            pass
        port.close()


# ---------- SysEx send / receive ----------

def _select_midi_port(names, spec, direction):
    if not names:
        raise RuntimeError(f"no MIDI {direction} ports found")
    if spec is None:
        if len(names) == 1:
            return names[0]
        listing = "\n".join(f"  {i}: {n}" for i, n in enumerate(names))
        raise ValueError(f"multiple MIDI {direction} ports found; choose one with --{'out-port' if direction == 'OUT' else 'in-port'}:\n" + listing)
    try:
        idx = int(spec)
    except ValueError:
        matches = [n for n in names if spec.lower() in n.lower()]
        if len(matches) != 1:
            raise ValueError(f"MIDI {direction} port '{spec}' did not match exactly one port")
        return matches[0]
    if idx < 0 or idx >= len(names):
        raise ValueError(f"MIDI {direction} port index out of range: {idx}")
    return names[idx]

def _split_sysex_file(path):
    data = Path(path).read_bytes()
    messages = []
    pos = 0
    while True:
        start = data.find(b"\xF0", pos)
        if start < 0:
            break
        end = data.find(b"\xF7", start + 1)
        if end < 0:
            raise ValueError(f"unterminated SysEx message at file offset 0x{start:X}")
        raw = data[start:end+1]
        if any(b >= 0x80 for b in raw[1:-1]):
            raise ValueError(f"invalid SysEx data byte >= 80H at/after file offset 0x{start:X}")
        messages.append(raw)
        pos = end + 1
    if not messages:
        raise ValueError("no complete F0...F7 SysEx message found")
    return messages

def _mido_sysex(raw):
    return mido.Message('sysex', data=tuple(raw[1:-1]))

def _x2_func(raw):
    """Return X2/X3 function byte for F0 42 3g 35 ... F7, else None."""
    if len(raw) >= 6 and raw[0] == 0xF0 and raw[1] == 0x42 \
            and (raw[2] & 0xF0) == 0x30 and raw[3] == 0x35 and raw[-1] == 0xF7:
        return raw[4]
    return None


# X2/X3 Reference Guide, MIDI Implementation:
# These received messages explicitly say they transmit Func=23 (ACK) or Func=24 (NAK).
_X2_ACK_NAK_FUNCS = {
    0x40: "PROGRAM PARAMETER DUMP",
    0x4C: "ALL PROGRAM PARAMETER DUMP",
    0x49: "COMBINATION PARAMETER DUMP",
    0x4D: "ALL COMBINATION PARAMETER DUMP",
    0x48: "ALL SEQUENCE DATA DUMP",
    0x51: "GLOBAL DATA DUMP",
    0x52: "DRUMS DATA DUMP",
    0x50: "ALL DATA DUMP",
    0x4E: "MODE CHANGE",
    0x41: "PARAMETER CHANGE",
    0x53: "DRUM KIT PARAMETER CHANGE",
}

# Write requests use a different completion pair: 21H / 22H.
_X2_WRITE_FUNCS = {
    0x11: "PROGRAM WRITE REQUEST",
    0x1A: "COMBINATION WRITE REQUEST",
}

# Dump/request messages return data (or 24H on failure), not ACK on success.
_X2_REQUEST_FUNCS = {
    0x10: "PROGRAM PARAMETER DUMP REQUEST",
    0x1F: "ALL DRUM SOUND NAME DUMP REQUEST",
    0x16: "ALL MULTISOUND NAME DUMP REQUEST",
    0x1C: "ALL PROGRAM PARAMETER DUMP REQUEST",
    0x19: "COMBINATION PARAMETER DUMP REQUEST",
    0x1D: "ALL COMBINATION PARAMETER DUMP REQUEST",
    0x18: "ALL SEQUENCE DATA DUMP REQUEST",
    0x0E: "GLOBAL DATA DUMP REQUEST",
    0x0D: "DRUMS DATA DUMP REQUEST",
    0x0F: "ALL DATA DUMP REQUEST",
    0x12: "MODE REQUEST",
}


def _x2_transaction(raw):
    """Describe the documented reply expected for an X2/X3 SysEx message."""
    func = _x2_func(raw)
    if func is None:
        return None, "not recognized as Korg X2/X3 SysEx", None
    if func in _X2_ACK_NAK_FUNCS:
        return "ack", _X2_ACK_NAK_FUNCS[func], func
    if func in _X2_WRITE_FUNCS:
        return "write", _X2_WRITE_FUNCS[func], func
    if func in _X2_REQUEST_FUNCS:
        return "data", _X2_REQUEST_FUNCS[func], func
    return None, f"X2/X3 Func={func:02X}H (reply rule not encoded)", func


def _x2_reply_kind(msg):
    if msg.type != 'sysex':
        return None
    d = bytes(msg.data)
    if len(d) < 4 or d[0] != 0x42 or (d[1] & 0xF0) != 0x30 or d[2] != 0x35:
        return None
    return {0x23: 'ACK', 0x24: 'NAK', 0x21: 'WRITE_OK',
            0x22: 'WRITE_ERROR', 0x26: 'FORMAT_ERROR'}.get(d[3])


def _wait_x2_status(inport, timeout, expected):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        for msg in inport.iter_pending():
            kind = _x2_reply_kind(msg)
            if kind:
                return kind
        time.sleep(0.005)
    return None



def _progress_line(label, done, total=None, width=32, estimated=False):
    """Single-line terminal progress display."""
    if total and total > 0:
        frac = max(0.0, min(1.0, done / total))
        n = int(frac * width)
        bar = "#" * n + "-" * (width - n)
        prefix = "~" if estimated else ""
        sys.stdout.write(
            f"\r{label} [{bar}] {frac*100:6.1f}%  {prefix}{int(done):,}/{int(total):,} bytes"
        )
    else:
        sys.stdout.write(f"\r{label} {int(done):,} bytes")
    sys.stdout.flush()


def _tx_progress_process(stop_event, total_bytes):
    """Draw estimated TX progress in a separate process.

    On Windows, a long RtMidi/WinMM send can block Python threads from
    repainting the console. A helper process keeps the display moving without
    changing the MIDI transmission itself.

    "~" marks the byte count as estimated. 2800 bytes/s is deliberately
    conservative relative to the 3125 bytes/s physical MIDI wire ceiling.
    """
    t0 = time.perf_counter()
    while not stop_event.is_set():
        elapsed = time.perf_counter() - t0
        est = min(total_bytes - 1 if total_bytes > 1 else total_bytes,
                  int(elapsed * 2800.0))
        _progress_line("  TX", est, total_bytes, estimated=True)
        stop_event.wait(0.10)


def _send_with_progress(outport, msg, total_bytes):
    """Send one complete SysEx and keep an estimated TX display moving.

    The SysEx message is still passed to RtMidi as one intact message. It is
    never split or paced internally. The helper process is display-only.
    """
    progress = None
    stop_event = None

    try:
        stop_event = multiprocessing.Event()
        progress = multiprocessing.Process(
            target=_tx_progress_process,
            args=(stop_event, total_bytes),
            daemon=True,
        )
        progress.start()
    except Exception:
        # Progress is cosmetic; never let it interfere with MIDI transmission.
        progress = None
        stop_event = None

    t0 = time.perf_counter()
    try:
        outport.send(msg)
    finally:
        if stop_event is not None:
            stop_event.set()
        if progress is not None:
            progress.join(timeout=1.0)
            if progress.is_alive():
                progress.terminate()
                progress.join(timeout=0.5)

    dt = time.perf_counter() - t0
    _progress_line("  TX", total_bytes, total_bytes)
    print()
    return dt


def _winmm_input_names():
    """Return native Windows WinMM MIDI IN device names."""
    import ctypes
    from ctypes import wintypes

    winmm = ctypes.WinDLL("winmm")
    class MIDIINCAPSW(ctypes.Structure):
        _fields_ = [
            ("wMid", wintypes.WORD),
            ("wPid", wintypes.WORD),
            ("vDriverVersion", wintypes.UINT),
            ("szPname", wintypes.WCHAR * 32),
            ("dwSupport", wintypes.DWORD),
        ]

    winmm.midiInGetNumDevs.restype = wintypes.UINT
    winmm.midiInGetDevCapsW.argtypes = [
        ctypes.c_size_t, ctypes.POINTER(MIDIINCAPSW), wintypes.UINT
    ]
    names = []
    for i in range(winmm.midiInGetNumDevs()):
        caps = MIDIINCAPSW()
        rc = winmm.midiInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
        names.append(caps.szPname if rc == 0 else f"MIDI IN {i}")
    return names


def _select_native_winmm_input(spec):
    names = _winmm_input_names()
    if not names:
        raise RuntimeError("no Windows MIDI IN ports found")
    if spec is None:
        if len(names) == 1:
            return 0, names[0]
        raise RuntimeError(
            "multiple MIDI IN ports found; specify --in-port. "
            + "; ".join(f"{i}: {n}" for i, n in enumerate(names))
        )
    s = str(spec).strip()
    if s.isdigit():
        i = int(s)
        if not 0 <= i < len(names):
            raise ValueError(f"MIDI IN port index out of range: {i}")
        return i, names[i]
    hits = [(i, n) for i, n in enumerate(names) if s.lower() in n.lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no MIDI IN port matches {spec!r}")
    raise ValueError(
        f"ambiguous MIDI IN port {spec!r}: "
        + "; ".join(f"{i}: {n}" for i, n in hits)
    )


def _receive_winmm(args):
    """Receive SysEx with native WinMM long-input buffers on Windows.

    RtMidi's Windows input path has historically used a compile-time SysEx
    receive buffer limit.  Large X2/X3 dumps can therefore disappear before
    Mido ever sees them.  This receiver supplies its own 4096-byte WinMM
    MIDIHDR buffers and reassembles F0...F7 messages in Python.
    """
    import ctypes
    from ctypes import wintypes

    port_index, port_name = _select_native_winmm_input(args.in_port)
    winmm = ctypes.WinDLL("winmm")

    DWORD_PTR = ctypes.c_size_t
    HMIDIIN = wintypes.HANDLE

    class MIDIHDR(ctypes.Structure):
        pass
    PMIDIHDR = ctypes.POINTER(MIDIHDR)
    MIDIHDR._fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", DWORD_PTR),
        ("dwFlags", wintypes.DWORD),
        ("lpNext", PMIDIHDR),
        ("reserved", DWORD_PTR),
        ("dwOffset", wintypes.DWORD),
        ("dwReserved", DWORD_PTR * 8),
    ]

    CALLBACK_FUNCTION = 0x00030000
    MIM_LONGDATA = 0x3C4
    MIM_LONGERROR = 0x3C6
    MMSYSERR_NOERROR = 0
    MHDR_PREPARED = 0x00000002

    CALLBACK = ctypes.WINFUNCTYPE(
        None, HMIDIIN, wintypes.UINT, DWORD_PTR, DWORD_PTR, DWORD_PTR
    )

    winmm.midiInOpen.argtypes = [
        ctypes.POINTER(HMIDIIN), ctypes.c_size_t, DWORD_PTR, DWORD_PTR, wintypes.DWORD
    ]
    winmm.midiInOpen.restype = wintypes.UINT
    winmm.midiInPrepareHeader.argtypes = [HMIDIIN, PMIDIHDR, wintypes.UINT]
    winmm.midiInPrepareHeader.restype = wintypes.UINT
    winmm.midiInUnprepareHeader.argtypes = [HMIDIIN, PMIDIHDR, wintypes.UINT]
    winmm.midiInUnprepareHeader.restype = wintypes.UINT
    winmm.midiInAddBuffer.argtypes = [HMIDIIN, PMIDIHDR, wintypes.UINT]
    winmm.midiInAddBuffer.restype = wintypes.UINT
    winmm.midiInStart.argtypes = [HMIDIIN]
    winmm.midiInStart.restype = wintypes.UINT
    winmm.midiInStop.argtypes = [HMIDIIN]
    winmm.midiInStop.restype = wintypes.UINT
    winmm.midiInReset.argtypes = [HMIDIIN]
    winmm.midiInReset.restype = wintypes.UINT
    winmm.midiInClose.argtypes = [HMIDIIN]
    winmm.midiInClose.restype = wintypes.UINT

    q = queue.Queue()
    headers = []
    buffers = []
    header_by_addr = {}

    @CALLBACK
    def callback(hmi, wmsg, instance, param1, param2):
        if wmsg not in (MIM_LONGDATA, MIM_LONGERROR) or not param1:
            return
        hp = ctypes.cast(param1, PMIDIHDR)
        n = int(hp.contents.dwBytesRecorded)
        data = ctypes.string_at(hp.contents.lpData, n) if n else b""
        q.put((ctypes.addressof(hp.contents), data, wmsg == MIM_LONGERROR))

    hmi = HMIDIIN()
    rc = winmm.midiInOpen(
        ctypes.byref(hmi), port_index,
        ctypes.cast(callback, ctypes.c_void_p).value, 0, CALLBACK_FUNCTION
    )
    if rc != MMSYSERR_NOERROR:
        raise RuntimeError(f"midiInOpen failed: WinMM error {rc}")

    # Smallish buffers give exact, visible RX progress while still leaving
    # enough buffers queued to avoid gaps at standard MIDI speed.
    BUF_SIZE = 4096
    BUF_COUNT = 16

    def check(rc, what):
        if rc != MMSYSERR_NOERROR:
            raise RuntimeError(f"{what} failed: WinMM error {rc}")

    received = []
    current = bytearray()
    total_rx = 0
    started = time.perf_counter()
    first_data_time = None
    last_data_time = None
    long_errors = 0

    try:
        for i in range(BUF_COUNT):
            buf = ctypes.create_string_buffer(BUF_SIZE)
            hdr = MIDIHDR()
            hdr.lpData = ctypes.cast(buf, ctypes.c_void_p).value
            hdr.dwBufferLength = BUF_SIZE
            hdr.dwBytesRecorded = 0
            hdr.dwUser = i
            buffers.append(buf)
            headers.append(hdr)
            header_by_addr[ctypes.addressof(hdr)] = hdr
            check(winmm.midiInPrepareHeader(hmi, ctypes.byref(hdr), ctypes.sizeof(hdr)),
                  "midiInPrepareHeader")
            check(winmm.midiInAddBuffer(hmi, ctypes.byref(hdr), ctypes.sizeof(hdr)),
                  "midiInAddBuffer")

        check(winmm.midiInStart(hmi), "midiInStart")
        print(f"MIDI IN : {port_name}  (native WinMM large-SysEx receiver)")
        print(f"Output  : {args.output}")
        print(f"Buffers : {BUF_COUNT} x {BUF_SIZE:,} bytes")
        print("Waiting for SysEx...  (Ctrl+C to stop)", flush=True)

        stop = False
        while not stop:
            now = time.perf_counter()
            try:
                addr, chunk, had_error = q.get(timeout=0.05)
            except queue.Empty:
                if args.timeout and first_data_time is None and now - started >= args.timeout:
                    break
                if (args.idle_timeout and first_data_time is not None
                        and last_data_time is not None
                        and now - last_data_time >= args.idle_timeout):
                    break
                continue

            if had_error:
                long_errors += 1

            if chunk:
                if first_data_time is None:
                    first_data_time = now
                last_data_time = now
                total_rx += len(chunk)
                _progress_line("  RX", total_rx)

                # Reassemble one or more F0...F7 messages from WinMM chunks.
                for b in chunk:
                    if not current:
                        if b == 0xF0:
                            current.append(b)
                    else:
                        if b == 0xF0:
                            # Resync if a new SysEx starts unexpectedly.
                            current.clear()
                            current.append(b)
                        else:
                            current.append(b)
                            if b == 0xF7:
                                raw = bytes(current)
                                received.append(raw)
                                current.clear()
                                print()
                                func = _x2_func(raw)
                                if func is not None:
                                    _, desc, _ = _x2_transaction(raw)
                                    print(
                                        f"Received SysEx {len(received)}: "
                                        f"{len(raw):,} bytes  X2/X3 {func:02X}H {desc}"
                                    )
                                else:
                                    print(
                                        f"Received SysEx {len(received)}: "
                                        f"{len(raw):,} bytes"
                                    )
                                if args.count and len(received) >= args.count:
                                    stop = True
                                    break

            # Put this long-data buffer back into the WinMM input queue.
            hdr = header_by_addr.get(addr)
            if hdr is not None and not stop:
                hdr.dwBytesRecorded = 0
                check(winmm.midiInAddBuffer(hmi, ctypes.byref(hdr), ctypes.sizeof(hdr)),
                      "midiInAddBuffer")

        if total_rx:
            print()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        winmm.midiInStop(hmi)
        winmm.midiInReset(hmi)
        # Give reset callbacks a moment to return outstanding buffers.
        time.sleep(0.05)
        for hdr in headers:
            if hdr.dwFlags & MHDR_PREPARED:
                winmm.midiInUnprepareHeader(hmi, ctypes.byref(hdr), ctypes.sizeof(hdr))
        winmm.midiInClose(hmi)

    if long_errors:
        print(f"Warning: WinMM reported {long_errors} long-data error buffer(s).",
              file=sys.stderr)
    if current:
        print(f"Warning: incomplete SysEx fragment: {len(current):,} bytes (no F7)",
              file=sys.stderr)
    if not received:
        raise RuntimeError(
            "no complete SysEx received. On Windows, SyX2ool used native WinMM "
            "large-SysEx buffers; check the X2 dump operation and MIDI cabling."
        )

    Path(args.output).write_bytes(b"".join(received))
    print(
        f"Saved {len(received)} SysEx message(s), "
        f"{sum(len(x) for x in received):,} bytes -> {args.output}"
    )

def send_cmd(args):
    require_mido()
    if args.delay < 0 or args.reply_timeout <= 0:
        raise ValueError("--delay must be >= 0 and --reply-timeout must be > 0")
    messages = _split_sysex_file(args.input)
    out_name = _select_midi_port(mido.get_output_names(), args.out_port, 'OUT')

    transactions = [_x2_transaction(raw) for raw in messages]
    need_reply = any(kind in ('ack', 'write') for kind, _, _ in transactions)
    monitor = (not args.no_reply) and need_reply
    inport = None
    in_name = None
    if monitor:
        in_name = _select_midi_port(mido.get_input_names(), args.in_port, 'IN')
        inport = mido.open_input(in_name)

    outport = mido.open_output(out_name)
    try:
        print(f"MIDI OUT: {out_name}")
        if in_name:
            print(f"MIDI IN : {in_name}  (X2/X3 completion monitor)")
        print(f"SysEx   : {args.input}  {len(messages)} message(s), {sum(len(x) for x in messages)} bytes")
        if args.delay:
            print(f"Delay   : {args.delay:g} ms between complete SysEx messages")

        for i, (raw, tx) in enumerate(zip(messages, transactions), 1):
            kind, desc, func = tx
            if inport is not None:
                for _ in inport.iter_pending():
                    pass

            tag = f"  X2/X3 {func:02X}H {desc}" if func is not None else f"  {desc}"
            print(f"Sending {i}/{len(messages)}: {len(raw)} bytes{tag}", flush=True)
            dt = _send_with_progress(outport, _mido_sysex(raw), len(raw))
            print(f"  MIDI send call completed in {dt:.3f} s")

            if kind == 'ack':
                if args.no_reply:
                    print("  Reply: not monitored (--no-reply)")
                else:
                    reply = _wait_x2_status(inport, args.reply_timeout, 'ack')
                    if reply == 'ACK':
                        print("  X2/X3: ACK (23H) — data load/processing completed")
                    elif reply == 'NAK':
                        raise RuntimeError("X2/X3 returned NAK (24H) — data load/processing failed")
                    elif reply == 'FORMAT_ERROR':
                        raise RuntimeError("X2/X3 returned MIDI IN DATA FORMAT ERROR (26H)")
                    elif reply in ('WRITE_OK', 'WRITE_ERROR'):
                        raise RuntimeError(f"unexpected X2/X3 reply: {reply}")
                    else:
                        msg = f"no documented ACK/NAK within {args.reply_timeout:g} s"
                        print("  X2/X3: " + msg, file=sys.stderr)
                        if args.require_reply:
                            raise RuntimeError(msg)
            elif kind == 'write':
                if args.no_reply:
                    print("  Reply: not monitored (--no-reply)")
                else:
                    reply = _wait_x2_status(inport, args.reply_timeout, 'write')
                    if reply == 'WRITE_OK':
                        print("  X2/X3: WRITE COMPLETED (21H)")
                    elif reply == 'WRITE_ERROR':
                        raise RuntimeError("X2/X3 returned WRITE ERROR (22H)")
                    elif reply == 'FORMAT_ERROR':
                        raise RuntimeError("X2/X3 returned MIDI IN DATA FORMAT ERROR (26H)")
                    elif reply in ('ACK', 'NAK'):
                        raise RuntimeError(f"unexpected X2/X3 reply: {reply}")
                    else:
                        msg = f"no documented WRITE COMPLETED/ERROR within {args.reply_timeout:g} s"
                        print("  X2/X3: " + msg, file=sys.stderr)
                        if args.require_reply:
                            raise RuntimeError(msg)
            elif kind == 'data':
                print("  Reply: request command; success returns DATA, not ACK (send does not capture it)")
            else:
                print("  Reply: no ACK assumption; transmission only")

            if i < len(messages) and args.delay:
                time.sleep(args.delay / 1000.0)
    finally:
        outport.close()
        if inport is not None:
            inport.close()

def receive_cmd(args):
    require_mido()
    if args.count is not None and args.count <= 0:
        raise ValueError("--count must be > 0")
    if args.timeout is not None and args.timeout <= 0:
        raise ValueError("--timeout must be > 0")
    if args.idle_timeout is not None and args.idle_timeout <= 0:
        raise ValueError("--idle-timeout must be > 0")

    # On Windows, bypass RtMidi for input.  Its WinMM SysEx receive buffer has
    # historically been compile-time limited, which can silently drop large
    # X2/X3 dumps.  Native WinMM long buffers also let us show exact RX bytes.
    if sys.platform.startswith("win"):
        return _receive_winmm(args)

    names = mido.get_input_names()
    name = _select_midi_port(names, args.in_port, 'IN')
    received = []
    print(f"MIDI IN : {name}")
    print(f"Output  : {args.output}")
    print("Waiting for SysEx..." + (f" timeout={args.timeout:g}s" if args.timeout else "  (Ctrl+C to stop)"))
    started = time.perf_counter()
    last_rx = None
    try:
        with mido.open_input(name) as port:
            while True:
                msg = port.poll()
                now = time.perf_counter()
                if msg is not None:
                    if msg.type == 'sysex':
                        raw = bytes((0xF0,)) + bytes(msg.data) + bytes((0xF7,))
                        received.append(raw)
                        last_rx = now
                        kind = _x2_reply_kind(msg)
                        suffix = f" [{kind}]" if kind else ""
                        print(f"Received SysEx {len(received)}: {len(raw):,} bytes{suffix}")
                        if args.count and len(received) >= args.count:
                            break
                    continue
                if args.timeout and now - started >= args.timeout and not received:
                    break
                if args.idle_timeout and last_rx is not None and now - last_rx >= args.idle_timeout:
                    break
                time.sleep(0.005)
    except KeyboardInterrupt:
        print("\nStopped.")
    if not received:
        raise RuntimeError("no SysEx received")
    Path(args.output).write_bytes(b''.join(received))
    print(f"Saved {len(received)} SysEx message(s), {sum(len(x) for x in received)} bytes -> {args.output}")

# ---------- CLI ----------

def build_parser():
    p = argparse.ArgumentParser(
        prog="syx2ool",
        description=f"SyX2ool v{VERSION} — Korg X2/X3 SysEx & MIDI Toolkit",
        epilog=(
            "Quick examples:\n"
            "  syx2ool import song.mid out.syx\n"
            "  syx2ool import song.mid out.syx --song 3 --template old.syx\n"
            "  syx2ool export dump.syx --song 0,3,9\n"
            "  syx2ool export dump.syx --pattern 0-19,30-35\n"
            "  syx2ool export dump.syx --all\n"
            "  syx2ool analyze dump.syx\n"
            "  syx2ool ports\n"
            "  syx2ool play song.mid --port 0\n"
            "  syx2ool play X3DRUMS.syx --pattern 0 --bpm 116 --loop\n"
            "  syx2ool send dump.syx --out-port 0 --in-port 0\n"
            "  syx2ool receive captured.syx --in-port 0\n\n"
            "Use 'syx2ool <command> -h' for command-specific help."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"SyX2ool {VERSION}")
    sub = p.add_subparsers(dest="command", metavar="{import,export,analyze,ports,play,send,receive}")

    pi = sub.add_parser(
        "import",
        help="convert an SMF to an X2/X3 Song",
        description=(
            "Import a Standard MIDI File into an X2/X3 ALL SEQUENCE DATA dump.\n"
            "The default target is S9; use --song 0..9 to choose another slot.\n"
            "Without --template, the embedded canonical empty sequencer image is used."
        ),
        epilog=(
            "Examples:\n"
            "  syx2ool import Physical.mid Physical.syx\n"
            "  syx2ool import song.mid out.syx --song 3\n"
            "  syx2ool import song.mid out.syx --song 3 --template existing.syx\n"
            "  syx2ool import song.mid out.syx --name MYSONG\n\n"
            "v0.1 import limits: SMF Format 0, 96 PPQN, constant 4/4,\n"
            "one constant tempo. Existing Songs/Patterns are preserved when\n"
            "--template is used, except for the selected target Song."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pi.add_argument("input", help="input Standard MIDI File (.mid)")
    pi.add_argument("output", help="output X2/X3 ALL SEQUENCE DATA SysEx (.syx)")
    pi.add_argument("-s", "--song", type=int, choices=range(10), default=9,
                    metavar="N", help="target Song S0..S9 (default: 9)")
    pi.add_argument("-t", "--template", metavar="DUMP.SYX",
                    help="existing 48H dump to modify; other Songs/Patterns are preserved")
    pi.add_argument("-n", "--name", metavar="NAME",
                    help="override X2/X3 Song Name (maximum 10 characters)")
    pi.set_defaults(func=import_song)

    pe = sub.add_parser(
        "export",
        help="export Songs and/or User Patterns as SMF",
        description=(
            "Export selected Songs and User Patterns from an X2/X3 48H dump.\n"
            "Selectors accept commas and ranges: 0,3,9  /  0-3,7,9.\n"
            "Pattern MIDI keeps X2/X3 note numbers and does NOT perform GM drum remapping."
        ),
        epilog=(
            "Examples:\n"
            "  syx2ool export dump.syx --song 9\n"
            "  syx2ool export dump.syx --song 0,3,9\n"
            "  syx2ool export dump.syx --song 0-3,7,9\n"
            "  syx2ool export dump.syx --songs\n"
            "  syx2ool export dump.syx --pattern 20,21,22\n"
            "  syx2ool export dump.syx --pattern 0-19,30-35,90-94\n"
            "  syx2ool export dump.syx --patterns\n"
            "  syx2ool export dump.syx --all\n\n"
            "--songs and --patterns select only non-empty objects.\n"
            "Pattern Put expansion is not yet implemented in v0.1."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pe.add_argument("input", help="input X2/X3 48H ALL SEQUENCE DATA SysEx (.syx)")
    pe.add_argument("--song", metavar="LIST",
                    help="Song selection, e.g. 9 or 0,3,9 or 0-3,7,9")
    pe.add_argument("--songs", action="store_true",
                    help="export every non-empty Song")
    pe.add_argument("--pattern", metavar="LIST",
                    help="Pattern selection, e.g. 20 or 20,21,22 or 0-19,30-35")
    pe.add_argument("--patterns", action="store_true",
                    help="export every non-empty User Pattern")
    pe.add_argument("--all", action="store_true",
                    help="export every non-empty Song and User Pattern")
    pe.add_argument("-o", "--output-dir", metavar="DIR",
                    help="output directory (default: <input_stem>_export)")
    pe.add_argument("-q", "--quiet", action="store_true",
                    help="suppress unsupported-event detail warnings")
    pe.set_defaults(func=export_cmd)

    pa = sub.add_parser(
        "analyze",
        help="inspect Song/Track/Pattern layout without modifying the dump",
        description=(
            "Inspect an X2/X3 48H ALL SEQUENCE DATA dump.\n"
            "Shows Song names, tempos, non-empty tracks, addresses and User Pattern usage."
        ),
        epilog="Example:\n  syx2ool analyze dump.syx",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pa.add_argument("input", help="input X2/X3 48H ALL SEQUENCE DATA SysEx (.syx)")
    pa.set_defaults(func=analyze_cmd)

    pports = sub.add_parser(
        "ports",
        help="list available MIDI IN/OUT ports",
        description="List MIDI OUT and MIDI IN ports available to SyX2ool.",
        epilog="Example:\n  syx2ool ports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pports.set_defaults(func=ports_cmd)

    pp = sub.add_parser(
        "play",
        help="play an SMF or X2/X3 User Pattern through MIDI OUT",
        description=(
            "Play a Standard MIDI File through a MIDI OUT port, or play one User Pattern\n"
            "directly from an X2/X3 48H ALL SEQUENCE DATA SysEx dump. SMF MIDI channels\n"
            "are preserved unless --channel is specified."
        ),
        epilog=(
            "Examples:\n"
            "  syx2ool ports\n  syx2ool play --list-ports\n"
            "  syx2ool play song.mid --port 0\n"
            "  syx2ool play P00.mid --port 0 --bpm 116 --loop\n"
            "  syx2ool play P00.mid --port 0 --channel 1\n"
            "  syx2ool play X3DRUMS.syx --pattern 0 --port 0 --bpm 116 --loop\n\n"
            "--bpm overrides SMF tempo while preserving tick timing.\n"
            "--channel remaps all channel messages to one MIDI channel; omit it for GM files.\n"
            "--timing-log prints absolute scheduler diagnostics at each loop boundary.\n"
            "Ctrl+C stops playback; All Notes Off is sent on exit."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pp.add_argument("input", nargs="?", help="input Standard MIDI File (.mid) or X2/X3 48H dump (.syx)")
    pp.add_argument("--pattern", type=int, metavar="N", help="with .syx input, play User Pattern P00..P99")
    pp.add_argument("--port", metavar="PORT", help="MIDI OUT port index or unique name substring")
    pp.add_argument("--list-ports", action="store_true", help="list available MIDI OUT ports and exit")
    pp.add_argument("--bpm", type=float, metavar="BPM", help="override SMF tempo")
    pp.add_argument("--channel", type=int, choices=range(1,17), metavar="CH", help="remap all channel messages to CH1..CH16")
    pp.add_argument("--loop", action="store_true", help="repeat until Ctrl+C")
    pp.add_argument("--timing-log", action="store_true", help="print each loop boundary expected/actual time and error")
    pp.set_defaults(func=play_cmd)

    ps = sub.add_parser(
        "send", help="send SysEx with X2/X3-aware completion monitoring",
        description=(
            "Send one or more complete F0...F7 SysEx messages through MIDI OUT.\n"
            "For Korg X2/X3 messages, SyX2ool inspects the function byte and waits\n"
            "only for the completion response documented for that function. Data-load\n"
            "commands use ACK/NAK (23H/24H); write requests use 21H/22H. Request\n"
            "commands return data rather than ACK. Unknown SysEx is simply sent."
        ),
        epilog=(
            "Examples:\n"
            "  syx2ool send dump.syx --out-port 0 --in-port 0\n"
            "  syx2ool send dump.syx --out-port Onyx --in-port Onyx --reply-timeout 10\n"
            "  syx2ool send multi.syx --out-port 0 --in-port 0 --delay 100\n"
            "  syx2ool send dump.syx --out-port 0 --no-reply\n\n"
            "--delay adds a pause only BETWEEN complete SysEx messages; it never\n"
            "splits a large single SysEx message. --reply-timeout controls how long\n"
            "to wait when the X2/X3 MIDI implementation documents a completion reply."
        ), formatter_class=argparse.RawDescriptionHelpFormatter)
    ps.add_argument("input", help="input .syx/.sys file containing F0...F7 message(s)")
    ps.add_argument("--out-port", metavar="PORT", help="MIDI OUT port index or unique name substring")
    ps.add_argument("--in-port", metavar="PORT", help="MIDI IN port for documented X2/X3 completion replies (default: sole input)")
    ps.add_argument("--delay", type=float, default=50.0, metavar="MS", help="pause between complete SysEx messages (default: 50 ms)")
    ps.add_argument("--reply-timeout", type=float, default=5.0, metavar="SEC", help="wait time for a documented X2/X3 completion reply (default: 5 s)")
    ps.add_argument("--require-reply", action="store_true", help="treat a missing documented completion reply as an error")
    ps.add_argument("--no-reply", action="store_true", help="do not open MIDI IN or wait for completion replies")
    ps.set_defaults(func=send_cmd)

    pr = sub.add_parser(
        "receive", help="receive SysEx from MIDI IN and save it",
        description="Receive SysEx from MIDI IN. On Windows, native WinMM long buffers are used for large X2/X3 dumps.",
        epilog=(
            "Examples:\n"
            "  syx2ool receive dump.syx --in-port 0\n"
            "  syx2ool receive dump.syx --in-port Onyx --count 1\n"
            "  syx2ool receive dump.syx --in-port 0 --timeout 30 --idle-timeout 2"
        ), formatter_class=argparse.RawDescriptionHelpFormatter)
    pr.add_argument("output", help="output .syx file")
    pr.add_argument("--in-port", metavar="PORT", help="MIDI IN port index or unique name substring")
    pr.add_argument("--count", type=int, metavar="N", help="stop after N SysEx messages")
    pr.add_argument("--timeout", type=float, metavar="SEC", help="stop if no first SysEx arrives within SEC")
    pr.add_argument("--idle-timeout", type=float, default=2.0, metavar="SEC", help="after receiving starts, stop after SEC of silence (default: 2)")
    pr.set_defaults(func=receive_cmd)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        args.func(args)
        return 0
    except Exception as e:
        print(f"syx2ool: error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
