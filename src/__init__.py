"""Where Songs Meet: parse MIDI, export .mcr, play with keyboard."""

from src.midi import (
    build_mcr_lines,
    export_mcr,
    map_note_to_key,
    parse_midi,
)

__all__ = [
    'build_mcr_lines',
    'export_mcr',
    'map_note_to_key',
    'parse_midi',
]
