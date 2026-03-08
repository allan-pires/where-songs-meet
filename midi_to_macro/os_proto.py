"""
Minimal decoder for Online Sequencer sequence binary (protobuf-like).
Extracts notes and builds MIDI. Sequence has repeated Note messages.
Note: type (enum index 0-71), time (float), length (float), instrument (int), volume (float).
"""
from __future__ import annotations

import base64
import re
import struct
import tempfile
from typing import Any

# Note type index order from site: octaves 7 down to 2, within octave B down to C.
# pianoNotes = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"], j 11->0, i 7->2
# k=0 -> B7, k=1 -> A#7, ... k=11 -> C7, k=12 -> B6, ... k=71 -> C2
# MIDI pitch: B7=107, so pitch = 107 - type_index
PIANO_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Online Sequencer instrument ID -> display name (from onlinesequencer.net/wiki/Instruments).
# Unknown IDs (e.g. cloned instruments) fall back to "Instrument {id}".
OS_INSTRUMENT_NAMES: dict[int, str] = {
    0: "Electric Piano (Classic)",
    1: "Acoustic Guitar (Classic)",
    2: "Drum Kit",
    3: "Smooth Synth (Classic)",
    4: "Electric Guitar",
    5: "Bass Guitar (Classic)",
    6: "Synth Pluck",
    7: "Scifi",
    8: "Grand Piano (Classic)",
    9: "French Horn (Classic)",
    10: "Trombone (Classic)",
    11: "Violin (Classic)",
    12: "Cello (Classic)",
    13: "8-Bit Sine",
    14: "8-Bit Square",
    15: "8-Bit Sawtooth",
    16: "8-Bit Triangle",
    17: "Harpsichord",
    18: "Concert Harp",
    19: "Xylophone",
    20: "Pizzicato",
    21: "Steel Drums",
    22: "Sitar",
    23: "Flute",
    24: "Saxophone",
    25: "Ragtime Piano",
    26: "Music Box",
    27: "Synth Bass (Classic)",
    28: "Church Organ",
    29: "Slap Bass",
    30: "Pop Synth (Classic)",
    31: "Electric Drum Kit (Classic)",
    32: "Jazz Guitar",
    33: "Koto",
    34: "Vibraphone",
    35: "Muted E-Guitar",
    36: "808 Drum Kit",
    37: "808 Bass",
    38: "Distortion Guitar (Classic)",
    39: "8-Bit Drum Kit",
    40: "2013 Drum Kit",
    41: "Grand Piano",
    42: "909 Drum Kit",
    43: "Electric Piano",
    44: "Distortion Guitar",
    45: "Cello",
    46: "Violin",
    47: "Strings",
    48: "Bass",
    49: "Clean Guitar",
    50: "French Horn",
    51: "Trombone",
    52: "Smooth Synth",
    53: "2023 Drum Kit",
    54: "Bass Guitar",
    55: "Synthesizer",
    56: "Synth Bass",
    57: "Pop Synth",
    58: "Acoustic Guitar",
    59: "Lucent Choir",
    60: "EDM Kit",
    61: "Brass",
    62: "Rhodes",
}


def _note_type_index_to_midi(index: int) -> int:
    """Convert OS note type index (0-71) to MIDI note number. k=0 -> B7=107, k=71 -> C2=36."""
    if index < 0 or index > 71:
        return 60
    return 107 - index


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Read varint at pos; return (value, new_pos)."""
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 56:
            break
    return result, pos


def _read_tag(data: bytes, pos: int) -> tuple[int, int, int] | None:
    """Read tag at pos; return (field_number, wire_type, new_pos) or None."""
    if pos >= len(data):
        return None
    v, pos = _read_varint(data, pos)
    wire = v & 7
    field = v >> 3
    return (field, wire, pos)


# Wire types: 0=varint, 1=64bit, 2=length-delimited, 5=32bit
def _skip_value(data: bytes, pos: int, wire: int) -> int:
    if wire == 0:  # varint
        while pos < len(data) and (data[pos] & 0x80):
            pos += 1
        return pos + 1 if pos < len(data) else pos
    if wire == 1:  # fixed64
        return pos + 8
    if wire == 2:  # length-delimited
        n, pos = _read_varint(data, pos)
        return pos + n
    if wire == 5:  # fixed32
        return pos + 4
    return pos


def _read_float32(data: bytes, pos: int) -> float:
    return struct.unpack_from("<f", data, pos)[0]


def _read_float64(data: bytes, pos: int) -> float:
    return struct.unpack_from("<d", data, pos)[0]


def _parse_note_compact(data: bytes, pos: int, end: int) -> dict[str, Any] | None:
    """Parse compact note (field-2 block). Field 1=pitch (MIDI 24-107 or type_index 0-71), 2=time, 3=length, 4=instrument, 5=volume."""
    note: dict[str, Any] = {}
    while pos < end:
        tag = _read_tag(data, pos)
        if not tag:
            break
        field, wire, pos = tag
        if wire == 0:
            v, pos = _read_varint(data, pos)
            if field == 1:
                # Compact format stores pitch as MIDI note (24-107); outside that use as type_index (0-71)
                if 24 <= v <= 107:
                    note["midi_note"] = v
                else:
                    note["type_index"] = v
            elif field == 4:
                note["instrument"] = v
        elif wire == 5:
            if pos + 4 <= end:
                f = _read_float32(data, pos)
                if field == 2:
                    note["time"] = f
                elif field == 3:
                    note["length"] = f
                elif field == 5:
                    note["volume"] = f
            pos += 4
        elif wire == 2:
            n, pos = _read_varint(data, pos)
            pos += n
        else:
            pos = _skip_value(data, pos, wire)
    if "midi_note" in note or "type_index" in note:
        note.setdefault("time", 0)
        note.setdefault("length", 0.25)
        note.setdefault("instrument", 0)
        note.setdefault("volume", 1.0)
        note["_time_unit"] = "ms"  # compact format uses milliseconds
        return note
    return None


def _note_to_midi(note: dict[str, Any]) -> int:
    """Get MIDI note number from a parsed note (compact uses midi_note, blob uses type_index)."""
    if "midi_note" in note:
        return max(0, min(127, note["midi_note"]))
    return _note_type_index_to_midi(note.get("type_index", 0))


def _parse_note_inner(data: bytes, pos: int, end: int) -> dict[str, Any] | None:
    """Parse inner note payload (e.g. 91 bytes): time, length, instrument, type_index, volume."""
    note: dict[str, Any] = {}
    while pos < end:
        tag = _read_tag(data, pos)
        if not tag:
            break
        field, wire, pos = tag
        if wire == 0:
            v, pos = _read_varint(data, pos)
            if field == 3:
                note["instrument"] = v
            elif field == 5:
                note["_f5"] = v
            elif field == 10:
                note["type_index"] = v
        elif wire == 2:
            n, pos = _read_varint(data, pos)
            pos += n
        elif wire == 5:
            if pos + 4 <= end:
                f = _read_float32(data, pos)
                if field == 1:
                    note["time"] = f
                elif field == 6:
                    note["length"] = f
                elif field == 11:
                    note["volume"] = f
            pos += 4
        elif wire == 1:
            pos += 8
        else:
            pos = _skip_value(data, pos, wire)
    if "type_index" in note:
        note.setdefault("time", 0)
        note.setdefault("length", 0.25)
        note.setdefault("instrument", 0)
        note.setdefault("volume", 1.0)
        note["_time_unit"] = "beats"  # blob inner format uses beats
        return note
    return None


def _parse_note_message(data: bytes, pos: int, end: int) -> dict[str, Any] | None:
    """Parse a single Note message (97 bytes): field 1 = ticks, field 2 = inner 91 bytes."""
    inner_start = None
    inner_len = None
    while pos < end:
        tag = _read_tag(data, pos)
        if not tag:
            break
        field, wire, pos = tag
        if field == 1 and wire == 0:
            pos = _skip_value(data, pos, wire)
        elif field == 2 and wire == 2:
            inner_len, pos = _read_varint(data, pos)
            inner_start = pos
            pos += inner_len
            break
        else:
            pos = _skip_value(data, pos, wire)
    if inner_start is not None and inner_len is not None:
        return _parse_note_inner(data, inner_start, inner_start + inner_len)
    return None


def get_sequence_instrument_name(inst_id: int) -> str:
    """Return display name for an Online Sequencer instrument ID. Unknown IDs use 'Instrument {id}'."""
    return OS_INSTRUMENT_NAMES.get(inst_id, f"Instrument {inst_id}")


def get_sequence_instruments(binary: bytes) -> list[tuple[int, str]]:
    """Return list of (instrument_id, display_name) for all instruments used in the sequence.
    Sorted by instrument id; display name uses OS instrument names when known."""
    notes = _parse_sequence_notes(binary)
    ids: set[int] = set()
    for n in notes:
        ids.add(n.get("instrument", 0))
    return [(i, get_sequence_instrument_name(i)) for i in sorted(ids)]


def _parse_sequence_notes(data: bytes) -> list[dict[str, Any]]:
    """Parse full sequence: field 1 = blob of notes (nested), field 2 = repeated compact notes. Collect all."""
    notes: list[dict[str, Any]] = []
    compact_notes: list[dict[str, Any]] = []
    pos = 0
    while pos < len(data):
        tag = _read_tag(data, pos)
        if not tag:
            break
        field, wire, pos = tag
        if wire == 2:
            n, pos = _read_varint(data, pos)
            sub_end = pos + n
            if sub_end > len(data):
                break
            if field == 1:
                # Blob: skip leading varint, then repeated field 3 (97-byte or variable note messages)
                sub = data[pos:sub_end]
                p = 0
                while p < len(sub):
                    t = _read_tag(sub, p)
                    if not t:
                        break
                    f, w, p = t
                    if f == 1 and w == 0:
                        p = _skip_value(sub, p, w)
                    elif f == 3 and w == 2:
                        L, p = _read_varint(sub, p)
                        note = _parse_note_message(sub, p, p + L)
                        if note:
                            notes.append(note)
                        p += L
                    else:
                        p = _skip_value(sub, p, w)
            elif field == 2:
                note = _parse_note_compact(data, pos, sub_end)
                if note:
                    compact_notes.append(note)
            pos = sub_end
        elif wire == 0:
            pos = _skip_value(data, pos, wire)
        elif wire == 5:
            pos += 4
        elif wire == 1:
            pos += 8
        else:
            pos = _skip_value(data, pos, wire)
    notes.extend(compact_notes)
    return notes


def _extract_bpm(binary: bytes) -> float | None:
    """Try to find a plausible BPM (60-300) in the first part of the sequence binary. Returns None if not found."""
    for offset in range(min(500, len(binary) - 4)):
        try:
            val = struct.unpack_from("<f", binary, offset)[0]
            if 60 <= val <= 300:
                return float(val)
        except Exception:
            pass
    return None


def _sequence_binary_from_page(html: str) -> bytes | None:
    """Extract and decode the 'var data = ...' base64 from sequence page HTML."""
    m = re.search(r"var data = '([^']*)'", html)
    if not m:
        m = re.search(r'var data = "([^"]*)"', html)
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        return base64.b64decode(raw)
    except Exception:
        return None


def sequence_binary_to_midi(
    binary: bytes,
    bpm: float = 110,
    output_path: str | None = None,
    instrument_ids: set[int] | None = None,
) -> str:
    """Convert decoded sequence binary to a MIDI file. Returns path to the created file.
    If instrument_ids is set, only notes from those instruments are included."""
    import mido
    from mido import MidiFile, MidiTrack, Message, MetaMessage, bpm2tempo

    notes = _parse_sequence_notes(binary)
    if not notes:
        raise ValueError("No notes found in sequence data")
    if instrument_ids is not None:
        notes = [n for n in notes if n.get("instrument", 0) in instrument_ids]
        if not notes:
            raise ValueError("No notes left after filtering by selected instruments")

    used_bpm = _extract_bpm(binary) or bpm
    ticks_per_beat = 384
    tempo = bpm2tempo(used_bpm)

    # Sort by (time, instrument, type_index) to approximate site export order (tracks then time)
    notes_sorted = sorted(
        notes,
        key=lambda n: (n.get("time", 0), n.get("instrument", 0), n.get("type_index", n.get("midi_note", 0))),
    )

    # For compact notes: scale so gaps match correct timing. 48 = 133 ms per 2 units; higher = slower.
    compact_times = [n.get("time", 0) for n in notes_sorted if n.get("_time_unit") == "ms"]
    min_compact_time = min(compact_times) if compact_times else 0
    COMPACT_TICKS_PER_UNIT = 124  # 2 units = 248 ticks ≈ 344 ms

    track = MidiTrack()
    track.append(MetaMessage("set_tempo", tempo=tempo))
    events: list[tuple[int, int, bool, int]] = []  # (time_ticks, midi_note, is_on, velocity)
    for n in notes_sorted:
        t = n.get("time", 0)
        length = n.get("length", 0.25)
        midi_note = _note_to_midi(n)
        vel = int(max(0, min(127, n.get("volume", 1) * 50)))
        if vel <= 0:
            vel = 64
        if n.get("_time_unit") == "ms":
            time_ticks = max(0, int(round((t - min_compact_time) * COMPACT_TICKS_PER_UNIT)))
            length_ticks = max(1, int(round(length * COMPACT_TICKS_PER_UNIT)))
        else:
            time_ticks = max(0, int(round(t * ticks_per_beat)))
            length_ticks = max(1, int(round(length * ticks_per_beat)))
        events.append((time_ticks, midi_note, True, vel))
        events.append((time_ticks + length_ticks, midi_note, False, 0))
    events.sort(key=lambda e: (e[0], not e[2]))  # note-off before note-on at same time

    last_ticks = 0
    for time_ticks, midi_note, is_on, vel in events:
        delta = max(0, time_ticks - last_ticks)
        last_ticks = time_ticks
        if is_on:
            track.append(Message("note_on", note=midi_note, velocity=vel, time=delta))
        else:
            track.append(Message("note_off", note=midi_note, velocity=0, time=delta))
    track.append(MetaMessage("end_of_track"))

    mid = MidiFile(ticks_per_beat=ticks_per_beat)
    mid.tracks.append(track)
    path = output_path or tempfile.NamedTemporaryFile(
        suffix=".mid", delete=False, prefix="os_"
    ).name
    mid.save(path)
    return path


def fetch_sequence_binary(sequence_id: str, timeout: float = 15) -> bytes:
    """Fetch sequence page and return decoded binary (protobuf)."""
    import urllib.request

    url = f"https://onlinesequencer.net/{sequence_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        html = r.read().decode("utf-8", errors="replace")
    binary = _sequence_binary_from_page(html)
    if not binary:
        raise ValueError("Could not extract sequence data from page")
    return binary


def download_sequence_midi(
    sequence_id: str,
    bpm: float = 110,
    timeout: float = 15,
    instrument_ids: set[int] | None = None,
) -> str:
    """Download a sequence by ID and convert to a temporary MIDI file. Returns path.
    If instrument_ids is set, only notes from those instruments are included."""
    binary = fetch_sequence_binary(sequence_id, timeout=timeout)
    return sequence_binary_to_midi(binary, bpm=bpm, instrument_ids=instrument_ids)
