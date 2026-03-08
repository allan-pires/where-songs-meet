"""Parse MIDI, map notes to keys, build .mcr lines, export."""

import mido

# Note range: row is chosen by pitch, not clamp. Low row < 60, mid 60–71, high 72+ (clamp note to 0–95).
NOTE_MIN = 0
NOTE_MAX = 95

# Keys per octave: 7 naturals then 5 blacks (with modifier)
LOW_KEYS = ['Z', 'X', 'C', 'V', 'B', 'N', 'M']   # low row
MID_KEYS = ['A', 'S', 'D', 'F', 'G', 'H', 'J']   # mid row
HIGH_KEYS = ['Q', 'W', 'E', 'R', 'T', 'Y', 'U']  # high row

# Black key semitones in an octave (C#=1, D#=3, F#=6, G#=8, A#=10)
BLACK = (1, 3, 6, 8, 10)


def _clamp_note(note: int) -> int:
    """Clamp note to mapped range (notes outside 0–95 get closest key)."""
    if note < NOTE_MIN:
        return NOTE_MIN
    if note > NOTE_MAX:
        return NOTE_MAX
    return note


def map_note_to_key(note: int) -> tuple[list[str], str]:
    """Map MIDI note number to (modifiers, key). Row by threshold: <60 low, 60–71 mid, 72+ high; pitch = note % 12."""
    note = _clamp_note(note)
    semitone = note % 12
    # 12 semitones -> 7 key indices (C,C#=0; D,D#=1; E=2; F,F#=3; G,G#=4; A,A#=5; B=6)
    key_index = (0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6)[semitone]
    if semitone in BLACK:
        # Black key: only X (D# on low row) uses CTRL; all others use SHIFT
        use_low_row = note < 60
        mods = ['CTRL'] if (use_low_row and key_index == 1) else ['SHIFT']
    else:
        mods = []
    if note < 60:
        key = LOW_KEYS[key_index]
    elif note < 72:
        key = MID_KEYS[key_index]
    else:
        key = HIGH_KEYS[key_index]
    return (mods, key)


def get_midi_track_info(path: str) -> list[tuple[int, str]]:
    """Return list of (track_index, track_name) for each track in the MIDI file.
    Track name is taken from the track_name meta message, or 'Track N' if missing."""
    mid = mido.MidiFile(path)
    result: list[tuple[int, str]] = []
    for i, track in enumerate(mid.tracks):
        name = f"Track {i}"
        for msg in track:
            if msg.type == "track_name" and hasattr(msg, "name"):
                name = msg.name or name
                break
        result.append((i, name))
    return result


def parse_midi(
    path: str,
    tempo_multiplier: float = 1.0,
    transpose: int = 0,
    track_indices: set[int] | None = None,
) -> list[tuple[int, list[str], str]]:
    """Parse MIDI file into events: (time_ms, modifiers, key).
    If track_indices is set, only notes from those tracks are included; otherwise all tracks."""
    mid = mido.MidiFile(path)
    ticks_per_beat = mid.ticks_per_beat
    tempo = 500_000  # default
    time_ticks = 0
    events: list[tuple[int, list[str], str]] = []
    tracks_to_merge = mid.tracks
    if track_indices is not None:
        tracks_to_merge = [mid.tracks[i] for i in range(len(mid.tracks)) if i in track_indices]
    for msg in mido.merge_tracks(tracks_to_merge):
        time_ticks += msg.time
        if msg.type == "set_tempo":
            tempo = msg.tempo
        if msg.type == "note_on" and getattr(msg, "velocity", 0) > 0:
            time_ms = int(mido.tick2second(time_ticks, ticks_per_beat, tempo) * 1000)
            time_ms = int(time_ms * tempo_multiplier)
            note = _clamp_note(msg.note + transpose)
            mods, key = map_note_to_key(note)
            events.append((time_ms, mods, key))
    return events


def build_mcr_lines(events: list[tuple[int, list[str], str]]) -> list[str]:
    """Build .mcr command lines from events. Chords: no delay between key down/up.
    A 2ms delay is inserted after modifier KeyDown so the game registers the modifier before the key.
    """
    lines: list[str] = []
    prev_time = 0
    MODIFIER_DELAY_MS = 2
    for time_ms, mods, key in events:
        delay = time_ms - prev_time
        if delay < 0:
            delay = 0
        lines.append(f'DELAY : {delay}')
        # Modifiers down
        for m in mods:
            if m == 'SHIFT':
                lines.append('Keyboard : ShiftLeft : KeyDown')
            elif m == 'CTRL':
                lines.append('Keyboard : ControlLeft : KeyDown')
        if mods:
            lines.append(f'DELAY : {MODIFIER_DELAY_MS}')
        # Key down/up (chord: no delay between)
        lines.append(f'Keyboard : {key} : KeyDown')
        lines.append(f'Keyboard : {key} : KeyUp')
        for m in reversed(mods):
            if m == 'SHIFT':
                lines.append('Keyboard : ShiftLeft : KeyUp')
            elif m == 'CTRL':
                lines.append('Keyboard : ControlLeft : KeyUp')
        prev_time = time_ms
    return lines


def export_mcr(path: str, events: list[tuple[int, list[str], str]]) -> None:
    """Write events to a .mcr file."""
    lines = build_mcr_lines(events)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
