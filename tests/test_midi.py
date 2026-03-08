"""Tests for where_songs_meet.midi: note mapping, MCR line building, export, parse."""

import pytest
from pathlib import Path

from where_songs_meet.midi import (
    build_mcr_lines,
    export_mcr,
    map_note_to_key,
    parse_midi,
)


class TestMapNoteToKey:
    """Test map_note_to_key row and modifier logic."""

    def test_low_row_natural(self):
        mods, key = map_note_to_key(48)  # C3
        assert mods == []
        assert key == 'Z'

    def test_mid_row_natural(self):
        mods, key = map_note_to_key(60)  # C4
        assert mods == []
        assert key == 'A'

    def test_high_row_natural(self):
        mods, key = map_note_to_key(72)  # C5
        assert mods == []
        assert key == 'Q'

    def test_black_key_shift(self):
        mods, key = map_note_to_key(61)  # C#4
        assert mods == ['SHIFT']
        assert key == 'A'

    def test_low_row_dsharp_ctrl(self):
        # D# on low row uses CTRL
        mods, key = map_note_to_key(51)  # D#3
        assert mods == ['CTRL']
        assert key == 'X'

    def test_note_clamped_high(self):
        mods, key = map_note_to_key(100)
        assert key == 'U'  # high row last key

    def test_note_clamped_low(self):
        mods, key = map_note_to_key(-5)
        assert key == 'Z'


class TestBuildMcrLines:
    """Test build_mcr_lines output format."""

    def test_single_note(self):
        events = [(0, [], 'Z')]
        lines = build_mcr_lines(events)
        assert lines[0] == 'DELAY : 0'
        assert 'Keyboard : Z : KeyDown' in lines
        assert 'Keyboard : Z : KeyUp' in lines

    def test_delay_between_notes(self):
        events = [(0, [], 'Z'), (100, [], 'X')]
        lines = build_mcr_lines(events)
        assert any(l == 'DELAY : 100' for l in lines)

    def test_modifier_delay(self):
        events = [(0, ['SHIFT'], 'Q')]
        lines = build_mcr_lines(events)
        assert 'DELAY : 2' in lines
        assert 'Keyboard : ShiftLeft : KeyDown' in lines
        assert 'Keyboard : ShiftLeft : KeyUp' in lines

    def test_chord_same_time(self):
        events = [(0, [], 'Z'), (0, [], 'X')]
        lines = build_mcr_lines(events)
        assert lines.count('DELAY : 0') >= 1


class TestExportMcr:
    """Test export_mcr writes valid file."""

    def test_writes_file(self, tmp_path):
        events = [(0, [], 'Z'), (50, ['SHIFT'], 'Q')]
        out = tmp_path / 'out.mcr'
        export_mcr(str(out), events)
        assert out.exists()
        content = out.read_text(encoding='utf-8')
        assert content.endswith('\n')
        assert 'DELAY : 0' in content
        assert 'Keyboard : Z : KeyDown' in content
        assert 'Keyboard : ShiftLeft : KeyDown' in content


class TestParseMidi:
    """Test parse_midi with optional sample file."""

    @pytest.fixture
    def sample_mid_path(self):
        p = Path(__file__).resolve().parent.parent / 'sample' / 'sample.mid'
        return p if p.exists() else None

    def test_parse_midi_returns_list(self, sample_mid_path):
        if not sample_mid_path:
            pytest.skip('sample/sample.mid not found')
        events = parse_midi(str(sample_mid_path))
        assert isinstance(events, list)

    def test_parse_midi_tempo_multiplier(self, sample_mid_path):
        if not sample_mid_path:
            pytest.skip('sample/sample.mid not found')
        events1 = parse_midi(str(sample_mid_path), tempo_multiplier=1.0)
        events2 = parse_midi(str(sample_mid_path), tempo_multiplier=2.0)
        if len(events1) >= 2 and len(events2) >= 2:
            t1 = events1[-1][0]
            t2 = events2[-1][0]
            assert t2 >= t1

    def test_parse_midi_transpose(self, sample_mid_path):
        if not sample_mid_path:
            pytest.skip('sample/sample.mid not found')
        events = parse_midi(str(sample_mid_path), transpose=12)
        assert isinstance(events, list)

    def test_parse_midi_invalid_path_raises(self):
        with pytest.raises((FileNotFoundError, OSError)):
            parse_midi('nonexistent_file_12345.mid')
