"""Tests for src.midi: note mapping, MCR line building, export, parse, GM/track groups."""

import pytest
from pathlib import Path

from src.midi import (
    GM_CATEGORIES,
    build_mcr_lines,
    export_mcr,
    get_file_track_groups_for_tracks,
    get_midi_track_info,
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


class TestGMCategories:
    """Test GM_CATEGORIES covers 0-127 and has expected names."""

    def test_covers_all_programs(self):
        all_progs = set()
        for _name, progs in GM_CATEGORIES:
            all_progs |= progs
        assert all_progs == set(range(128))

    def test_six_categories(self):
        assert len(GM_CATEGORIES) == 6
        names = [n for n, _ in GM_CATEGORIES]
        assert "Keys" in names
        assert "Other" in names


class TestGetFileTrackGroupsForTracks:
    """Test get_file_track_groups_for_tracks with synthetic tracks."""

    def test_empty_tracks(self):
        assert get_file_track_groups_for_tracks([]) == []

    def test_single_track_keys(self):
        tracks = [(0, "Piano", 0)]
        result = get_file_track_groups_for_tracks(tracks)
        assert len(result) == 1
        assert result[0][0] == "Keys"
        assert result[0][1] == {0}

    def test_multiple_categories(self):
        # prog 0=Keys, 25=Guitar& Bass range(24,40), 40=Strings
        tracks = [(0, "Piano", 0), (1, "Guitar", 25), (2, "Strings", 40)]
        result = get_file_track_groups_for_tracks(tracks)
        names = [r[0] for r in result]
        assert "Keys" in names
        assert "Guitar & Bass" in names
        assert "Strings" in names
        key_indices = next(r[1] for r in result if r[0] == "Keys")
        assert key_indices == {0}

    def test_track_index_preserved(self):
        tracks = [(3, "Synth", 80)]  # Synths
        result = get_file_track_groups_for_tracks(tracks)
        assert result[0][1] == {3}


class TestGetMidiTrackInfo:
    """Test get_midi_track_info with temp MIDI file."""

    def test_single_track_no_meta(self, tmp_path):
        import mido
        p = tmp_path / "t.mid"
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        track.append(mido.Message("program_change", program=5))
        mid.tracks.append(track)
        mid.save(str(p))
        info = get_midi_track_info(str(p))
        assert len(info) == 1
        assert info[0][0] == 0
        assert info[0][1] == "Track 0"
        assert info[0][2] == 5

    def test_track_name_and_program(self, tmp_path):
        import mido
        p = tmp_path / "t.mid"
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name="Bass"))
        track.append(mido.Message("program_change", program=33))
        mid.tracks.append(track)
        mid.save(str(p))
        info = get_midi_track_info(str(p))
        assert info[0][1] == "Bass"
        assert info[0][2] == 33
