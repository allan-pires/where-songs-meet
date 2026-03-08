# Where Songs Meet (Windows)

Convert MIDI files to macro (.mcr) command files and play them as keyboard input in real time. Includes support for local files, **onlinesequencer.net** sequences, a playlist, and synced “play together” rooms.

https://github.com/user-attachments/assets/2d31b7ef-e86d-4898-bdb0-3c005320545d



## Disclaimer

**This is a third-party product.** It does not modify any game files—it only simulates keyboard input. Nevertheless, game publishers may treat any automation or third-party tools as a violation of their terms of service, and **you can still be banned** if they decide to do so. Use at your own risk. **This tool is intended for personal use only.**

Also: this project is messy; it was full vibe coded. 🎹

## Features

- **Live playback** — MIDI notes are sent as keyboard input via pynput
- **Tempo & transpose** — Speed up/slow down and shift notes by semitones; settings can be saved per song
- **File tab** — Open a folder of .mid/.midi files and play or add to playlist
- **Online Sequencer tab** — Browse and search onlinesequencer.net, download MIDI, add to favorites or playlist
- **Playlist tab** — Queue songs from File or Online Sequencer and play in order
- **Play together** — Host or join a room; when the host presses Play, everyone starts in sync. Optional **public link** (ngrok) lets friends outside your network join.
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
4. **Play together** — **Host**: set port and start; **Join**: enter host:port. Host selects music and presses Play; clients start in sync. See below for playing with friends over the internet (ngrok).

### How to play together using ngrok (friends not on your network)

End-to-end flow so someone outside your LAN can join your room:

| Who | Steps |
|-----|--------|
| **Host (you)** | 1. In **Play together**, click **Host** to start the room.<br>2. Click **Create public link** and wait for the address (e.g. `0.tcp.ngrok.io:12345`).<br>3. Click **Copy** and send that address to your friend (chat, email, etc.).<br>4. Pick a song (File or Online Sequencer), assign instruments if needed, then press **Play** when everyone is ready. |
| **Friend** | 1. Open the app and go to **Play together**.<br>2. In **Join**, paste the address you received (e.g. `0.tcp.ngrok.io:12345`).<br>3. Click the connect button to join.<br>4. When the host presses Play, playback starts in sync. |

**One-time (host only):** Before **Create public link** works, set your ngrok token once: sign up at [ngrok.com](https://ngrok.com), copy your [authtoken](https://dashboard.ngrok.com/get-started/your-authtoken), then set `NGROK_AUTH_TOKEN` in Windows environment variables (or in PowerShell for that session). Restart the app after adding the variable. See *Playing with friends over the internet (ngrok)* below for details.

### Playing with friends over the internet (ngrok)

To let friends **not on your local network** join your room, use the built-in **public link** (ngrok TCP tunnel):

1. **One-time setup**
   - Sign up at [ngrok.com](https://ngrok.com) (free account).
   - In the [ngrok dashboard](https://dashboard.ngrok.com/get-started/your-authtoken), copy your **authtoken**.
   - Set the token so the app can see it:
     - **Option A (current session):** In PowerShell: `$env:NGROK_AUTH_TOKEN = "your-token-here"`
     - **Option B (permanent):** Windows **Settings → System → About → Advanced system settings → Environment variables**. Under *User variables*, add `NGROK_AUTH_TOKEN` with your token. Restart the app after adding it.
2. **When hosting**
   - Start the room as usual (**Host** with your port).
   - Click **Create public link**. After a few seconds, a public address appears (e.g. `0.tcp.ngrok.io:12345`).
   - Click **Copy** and send that address to your friends.
3. **Friends**
   - In **Join**, paste the address (e.g. `0.tcp.ngrok.io:12345`) and connect. No VPN or being on the same LAN required.

The tunnel closes when you stop hosting. Requires **pyngrok** (`pip install -r requirements.txt`).

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
- **Same network:** Allow the app in Windows Firewall (Private network) and use the host’s LAN IP and port (e.g. `192.168.0.1:38472`).  
- **Different networks:** Use **Create public link** (ngrok) when hosting and share the generated address; friends paste it in Join. Ensure `NGROK_AUTH_TOKEN` is set (see *Playing with friends over the internet* above).

**MIDI not loading?**  
- Use valid .mid or .midi files  
- For Online Sequencer, check your connection and try another sequence

## Project structure (development)

- **`main.py`** — Entry point; requests admin then starts the GUI  
- **`tools/build_exe.py`** — Build single-file Windows exe (PyInstaller)  
- **`.github/workflows/release.yml`** — On push of tag `v*`, builds exe and creates a GitHub release  
- **`midi-to-mcr.spec`** — PyInstaller spec (optional); preferred build is **`python tools/build_exe.py`**  
- **`src/`** — Core package  
  - **`midi.py`** — Parse MIDI, map notes to keys, build .mcr lines, export  
  - **`playback.py`** — Run playback from events or file (pynput)  
  - **`config.py`** — Config directory path (single source of truth for `~/.where_songs_meet`)  
  - **`sync.py`** — Room (host/join), LAN IP, play-together protocol  
  - **`tunnel.py`** — Public link via ngrok TCP tunnel for remote join  
  - **`song_settings.py`** — Per-song tempo/transpose persistence  
  - **`os_favorites.py`**, **`file_favorites.py`** — Favorites persistence (OS sequences, file paths)  
  - **`playlist.py`** — Playlist state (file/OS items, index)  
  - **`online_sequencer.py`** — Fetch/search sequences, download MIDI  
  - **`app.py`** — Tkinter GUI (main window and tabs)  
  - **`ui_controls.py`**, **`ui_helpers.py`** — Reusable controls (e.g. Play/Stop button), tooltips  
  - **`theme.py`** — UI constants  
  - **`version.py`** — App version and GitHub repo for update checks  
  - **`updater.py`** — Fetch latest release, compare version, open/download update  
  - **`admin.py`**, **`window_focus.py`** — Windows helpers  

Tests: `pytest tests/`

### Creating a release

1. Bump `__version__` in `src/version.py`.
2. Ensure `origin` points to the repo in `version.py` (allan-pires/where-songs-meet) so the in-app updater and releases match: `git remote -v` → origin should be `https://github.com/allan-pires/where-songs-meet.git`.
3. Commit, then push a tag: `git tag v1.0.4 && git push origin v1.0.4`.
4. GitHub Actions on that repo builds the Windows exe and creates a release with `where-songs-meet.exe` attached. “Download and run” in the app fetches from the same repo.
