# Where Songs Meet (Windows)

Convert MIDI files to macro (.mcr) command files and play them as keyboard input in real time. Includes support for local files, **onlinesequencer.net** sequences, a playlist, and synced “play together” rooms.

## Disclaimer

**This is a third-party product.** It does not modify any game files—it only simulates keyboard input. Nevertheless, game publishers may treat any automation or third-party tools as a violation of their terms of service, and **you can still be banned** if they decide to do so. Use at your own risk. **This tool is intended for personal use only.**

Also: this project is messy; it was full vibe coded. 🎹

## Features

- **Live playback** — MIDI notes are sent as keyboard input via pynput
- **Tempo & transpose** — Speed up/slow down and shift notes by semitones; settings can be saved per song
- **File tab** — Open a folder of .mid/.midi files and play or add to playlist
- **Online Sequencer tab** — Browse and search onlinesequencer.net, download MIDI, add to favorites or playlist
- **Playlist tab** — Queue songs from File or Online Sequencer and play in order
- **Play together** — Host or join a room; when the host presses Play, everyone starts in sync
- **Chord support** — Simultaneous key presses with correct modifier handling (Shift/Ctrl for black keys)
- **Check for updates** — Button in the header checks GitHub releases and can open the release page or download and run the latest build

## Installation

### From source

```bash
pip install -r requirements.txt
python main.py
```

### Executable

- **Build locally:** `pip install -r requirements-build.txt` then `python tools/build_exe.py`. Output: `dist/where-songs-meet.exe`. Run that executable.
- **Where Songs Meet** may request Administrator privileges for keyboard simulation (needed for games)

## Requirements

- Python 3.8+ (when running from source)
- **mido** — MIDI file parsing
- **pynput** — Keyboard simulation

## Usage

### GUI tabs

1. **File** — Choose a folder, select a MIDI file. Use **Tempo ×** and **Transpose**, then **Play** or **Add to playlist**. Optionally save tempo/transpose for the selected song.
2. **Online Sequencer** — Load or search sequences from onlinesequencer.net. Download, play, or add to playlist; manage favorites (★).
3. **Playlist** — Play queued songs in order. Add/remove/clear; play or stop from this tab.
4. **Play together** — **Host**: set port and start; **Join**: enter host:port. Host selects music and presses Play; clients start in sync.

### Key mappings

Notes are mapped by **pitch class** (note % 12) and **row by range**:

- **Low row** (notes &lt; 60): Z, X, C, V, B, N, M  
- **Mid row** (60–71): A, S, D, F, G, H, J  
- **High row** (72+): Q, W, E, R, T, Y, U  

Notes outside 0–95 are clamped. Black keys use **Shift** (or **Ctrl** for D♯ on the low row). Use **Transpose** to shift octaves.

## Important notes

### Administrator privileges

The app may need to run as Administrator so keyboard input reaches games. Windows will prompt when required.

### Game compatibility

- Works with standard Windows keyboard input (Notepad, browsers, many games)
- May not work with anti-cheat or raw-input-only games
- Tested with Where Winds Meet (admin mode)

### Performance

- Timing is derived from MIDI positions for accurate playback
- Chords use synchronized key down/up; a short delay after modifiers helps game registration

## Troubleshooting

**Keys not recognized in game?**  
- Run as Administrator and focus the game window before Play  
- Some games block simulated input

**Play together: others can’t connect?**  
- Allow the app in Windows Firewall (Private network)  
- Use the host’s LAN IP and the port shown (e.g. `192.168.0.1:38472`)

**MIDI not loading?**  
- Use valid .mid or .midi files  
- For Online Sequencer, check your connection and try another sequence

## Project structure (development)

- **`main.py`** — Entry point; requests admin then starts the GUI  
- **`tools/build_exe.py`** — Build single-file Windows exe (PyInstaller)  
- **`.github/workflows/release.yml`** — On push of tag `v*`, builds exe and creates a GitHub release  
- **`midi_to_macro/`** — Core package  
  - **`midi.py`** — Parse MIDI, map notes to keys, build .mcr lines, export  
  - **`playback.py`** — Run playback from events or file (pynput)  
  - **`sync.py`** — Room (host/join), LAN IP, play-together protocol  
  - **`song_settings.py`** — Per-song tempo/transpose persistence  
  - **`os_favorites.py`** — Online Sequencer favorites persistence  
  - **`playlist.py`** — Playlist state (file/OS items, index)  
  - **`online_sequencer.py`** — Fetch/search sequences, download MIDI  
  - **`app.py`** — Tkinter GUI  
  - **`theme.py`** — UI constants  
  - **`version.py`** — App version and GitHub repo for update checks  
  - **`updater.py`** — Fetch latest release, compare version, open/download update  
  - **`admin.py`**, **`window_focus.py`** — Windows helpers  

Tests: `pytest tests/`

### Creating a release

1. Bump `__version__` in `midi_to_macro/version.py`.
2. Ensure `origin` points to the repo in `version.py` (allan-pires/where-songs-meet) so the in-app updater and releases match: `git remote -v` → origin should be `https://github.com/allan-pires/where-songs-meet.git`.
3. Commit, then push a tag: `git tag v1.0.4 && git push origin v1.0.4`.
4. GitHub Actions on that repo builds the Windows exe and creates a release with `where-songs-meet.exe` attached. “Download and run” in the app fetches from the same repo.
