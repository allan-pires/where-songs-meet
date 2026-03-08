"""Play back events as keyboard input using pynput."""

import time
from typing import Callable

try:
    from pynput.keyboard import Controller, Key
    KEYBOARD_AVAILABLE = True
except ImportError:
    Controller = None
    Key = None
    KEYBOARD_AVAILABLE = False

# Map key letter to pynput Key or char
KEY_MAP = {
    'Q': 'q', 'W': 'w', 'E': 'e', 'R': 'r', 'T': 't', 'Y': 'y', 'U': 'u',
    'A': 'a', 'S': 's', 'D': 'd', 'F': 'f', 'G': 'g', 'H': 'h', 'J': 'j',
    'Z': 'z', 'X': 'x', 'C': 'c', 'V': 'v', 'B': 'b', 'N': 'n', 'M': 'm',
}


def run_playback(
    events: list[tuple[int, list[str], str]],
    is_playing: Callable[[], bool],
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """Run playback: sleep to time_ms then press modifiers + key. progress_callback(current_index, total)."""
    if not KEYBOARD_AVAILABLE:
        raise RuntimeError('pynput not available')
    ctrl = Controller()
    total = len(events)
    t0 = time.perf_counter()
    prev_ms = 0
    for i, (time_ms, mods, key) in enumerate(events):
        if not is_playing():
            return
        if progress_callback:
            progress_callback(i, total)
        # Wait until this event's time
        elapsed_ms = (time.perf_counter() - t0) * 1000
        wait_ms = time_ms - elapsed_ms
        if wait_ms > 0:
            time.sleep(wait_ms / 1000.0)
        # Press modifiers + key (chord: no delay)
        shift_down = 'SHIFT' in mods
        ctrl_down = 'CTRL' in mods
        if shift_down:
            ctrl.press(Key.shift)
        if ctrl_down:
            ctrl.press(Key.ctrl)
        char = KEY_MAP.get(key, key.lower())
        ctrl.press(char)
        ctrl.release(char)
        if ctrl_down:
            ctrl.release(Key.ctrl)
        if shift_down:
            ctrl.release(Key.shift)
    if progress_callback:
        progress_callback(total, total)


def run_playback_from_file(
    path: str,
    tempo_multiplier: float,
    transpose: int,
    is_playing: Callable[[], bool],
    progress_callback: Callable[[int, int], None] | None = None,
    done_callback: Callable[[bool], None] | None = None,
    track_indices: set[int] | None = None,
) -> None:
    """
    Parse MIDI file and run playback in the current thread.
    done_callback(finished_naturally) is called when playback ends (True if completed, False if stopped).
    If track_indices is set, only those tracks are played.
    """
    from src import midi
    finished_naturally = False
    try:
        events = midi.parse_midi(
            path,
            tempo_multiplier=tempo_multiplier,
            transpose=transpose,
            track_indices=track_indices,
        )
        if progress_callback:
            progress_callback(0, len(events))
        run_playback(events, is_playing, progress_callback=progress_callback)
        finished_naturally = True
    except Exception:
        raise
    finally:
        if done_callback:
            done_callback(finished_naturally)
