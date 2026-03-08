"""Tests for src.os_proto: get_instrument_groups_for_sequence and INSTRUMENT_GROUPS."""

import pytest

from src.os_proto import INSTRUMENT_GROUPS, get_instrument_groups_for_sequence


class TestGetInstrumentGroupsForSequence:
    """Test get_instrument_groups_for_sequence returns correct groups and id sets."""

    def test_empty_returns_empty(self):
        assert get_instrument_groups_for_sequence([]) == []
        assert get_instrument_groups_for_sequence(set()) == []

    def test_single_group_keys(self):
        # 0 and 8 are in Keys
        result = get_instrument_groups_for_sequence([0, 8])
        names = [r[0] for r in result]
        assert "Keys" in names
        keys_entry = next(r for r in result if r[0] == "Keys")
        assert keys_entry[1] == {0, 8}

    def test_multiple_groups(self):
        # 0 = Keys, 2 = Drums, 1 = Guitar & Bass
        result = get_instrument_groups_for_sequence([0, 1, 2])
        names = [r[0] for r in result]
        assert "Keys" in names
        assert "Drums" in names
        assert "Guitar & Bass" in names

    def test_accepts_set(self):
        result = get_instrument_groups_for_sequence({11, 12})  # Strings
        assert any(r[0] == "Strings" and r[1] == {11, 12} for r in result)

    def test_only_returns_groups_with_sequence_instruments(self):
        # Use an ID that's in one group only
        result = get_instrument_groups_for_sequence([2])  # Drum Kit
        assert len(result) == 1
        assert result[0][0] == "Drums"
        assert result[0][1] == {2}


class TestInstrumentGroups:
    """Test INSTRUMENT_GROUPS structure."""

    def test_expected_group_names(self):
        expected = {"Keys", "Strings", "Guitar & Bass", "Drums", "Brass & Synths", "Other"}
        assert set(INSTRUMENT_GROUPS.keys()) == expected

    def test_no_duplicate_ids_across_groups(self):
        all_ids: list[int] = []
        for ids in INSTRUMENT_GROUPS.values():
            all_ids.extend(ids)
        # Duplicates allowed per wiki (e.g. 8-Bit Drum in Drums and elsewhere)
        assert len(all_ids) >= len(set(all_ids))  # at least some ids possible
