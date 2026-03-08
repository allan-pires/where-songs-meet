"""Tkinter GUI application."""

import logging
from typing import Callable
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

log = logging.getLogger("src.app")

from src import midi, playback
from src.online_sequencer import (
    download_sequence_midi,
    fetch_sequences,
    open_sequence,
    search_sequences,
    SORT_OPTIONS,
)
from src.os_proto import (
    fetch_sequence_binary,
    get_sequence_instruments,
    sequence_binary_to_midi,
)
from src.os_favorites import OsFavorites
from src.playlist import Playlist
from src.song_settings import SongSettings
from src.sync import DEFAULT_PORT, Room, START_DELAY_SEC, get_lan_ip
from src.tunnel import get_public_addr, is_available, is_tunnel_active, start_tcp_tunnel, stop_tunnel
from src.firewall import add_firewall_rules
from src.updater import check_for_updates, download_update, is_newer, open_release_page
from src.version import __version__ as APP_VERSION
from src.window_focus import focus_process_window, get_foreground_process_name
from src import log_config as _log_config
from src import theme as _theme

_t = _theme
ACCENT = _t.ACCENT
ACCENT_HOVER = _t.ACCENT_HOVER
BG = _t.BG
BORDER = _t.BORDER
BTN_PAD = _t.BTN_PAD
BTN_GAP = _t.BTN_GAP
BTN_GAP_TIGHT = _t.BTN_GAP_TIGHT
BTN_PAD_LARGE = _t.BTN_PAD_LARGE
CARD = _t.CARD
CARD_BORDER = _t.CARD_BORDER
CTRL_BTN_GAP = _t.CTRL_BTN_GAP
ENTRY_BG = _t.ENTRY_BG
ENTRY_FG = _t.ENTRY_FG
FONT_FAMILY = _t.FONT_FAMILY
FG = _t.FG
FG_DISABLED = _t.FG_DISABLED
HINT_FONT = _t.HINT_FONT
HINT_WRAP = _t.HINT_WRAP
ICON_ADD_LIST = _t.ICON_ADD_LIST
ICON_ADD_TO_PLAYLIST = _t.ICON_ADD_TO_PLAYLIST
ICON_BROWSER = _t.ICON_BROWSER
ICON_CLEAR = _t.ICON_CLEAR
ICON_CONNECT = _t.ICON_CONNECT
ICON_DISCONNECT = _t.ICON_DISCONNECT
ICON_DOWNLOAD = _t.ICON_DOWNLOAD
ICON_FAV = _t.ICON_FAV
ICON_FAV_OFF = _t.ICON_FAV_OFF
ICON_FOLDER = _t.ICON_FOLDER
ICON_FONT = _t.ICON_FONT
ICON_HOST = _t.ICON_HOST
ICON_PLAY = _t.ICON_PLAY
ICON_RELOAD = _t.ICON_RELOAD
ICON_REMOVE = _t.ICON_REMOVE
ICON_SAVE = _t.ICON_SAVE
ICON_SEARCH = _t.ICON_SEARCH
ICON_STOP = _t.ICON_STOP
ICON_STOP_HOST = _t.ICON_STOP_HOST
ICON_BTN_WIDTH = _t.ICON_BTN_WIDTH
ICON_BTN_PADX = getattr(_t, 'ICON_BTN_PADX', (8, 8))
ICON_UPDATE = _t.ICON_UPDATE
ICON_LOG = _t.ICON_LOG
LISTBOX_MIN_ROWS = _t.LISTBOX_MIN_ROWS
OS_LISTBOX_MIN_ROWS = _t.OS_LISTBOX_MIN_ROWS
PAD = _t.PAD
PLAY_GREEN = _t.PLAY_GREEN
PLAY_GREEN_HOVER = _t.PLAY_GREEN_HOVER
SMALL_FONT = _t.SMALL_FONT
SMALL_PAD = _t.SMALL_PAD
STOP_RED = _t.STOP_RED
STOP_RED_HOVER = _t.STOP_RED_HOVER
SUBTLE = _t.SUBTLE
TAB_BG_UNSELECTED = _t.TAB_BG_UNSELECTED
TITLE_FONT = _t.TITLE_FONT
LABEL_FONT = _t.LABEL_FONT


# Play/Stop symbols (no Canvas — avoids Tk "bad argument 'N': must be name of window" on some builds)
_CTRL_PLAY_SYMBOL = '\u25b6'   # ▶
_CTRL_STOP_SYMBOL = '\u25a0'   # ■

# Control button shape: enough height for 1080p so play/stop glyph isn't clipped
_CTRL_BTN_W = 56
_CTRL_BTN_H = 40
_CTRL_BTN_R = 6


def _rounded_rect_photo(w: int, h: int, color_hex: str, radius: int):
    """Return a PhotoImage of a rounded rectangle (Pillow). Kept for GC."""
    try:
        from PIL import Image, ImageDraw, ImageTk
        img = Image.new("RGB", (w, h), color_hex)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=color_hex, outline=color_hex)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


class ControlButton(tk.Frame):
    """Play or Stop control button: rounded rect image if Pillow available, else flat tk.Button."""

    def __init__(self, parent, kind, bg, hover_bg, fg, command, initial_state=tk.NORMAL, disabled_bg=None):
        assert kind in ('play', 'stop'), kind
        self._bg = bg
        self._hover_bg = hover_bg
        self._disabled_bg = disabled_bg if disabled_bg is not None else CARD
        self._command = command
        self._state = initial_state
        self._kind = kind
        text = _CTRL_PLAY_SYMBOL if kind == 'play' else _CTRL_STOP_SYMBOL
        super().__init__(parent, bg=CARD)
        # Fixed size so button doesn't shrink when state changes (e.g. play disabled while playing)
        self.pack_propagate(False)
        tk.Frame.config(self, width=_CTRL_BTN_W, height=_CTRL_BTN_H)
        # Rounded-rect images (keep refs so they aren't GC'd)
        self._img_normal = _rounded_rect_photo(_CTRL_BTN_W, _CTRL_BTN_H, bg, _CTRL_BTN_R)
        self._img_hover = _rounded_rect_photo(_CTRL_BTN_W, _CTRL_BTN_H, hover_bg, _CTRL_BTN_R)
        self._img_disabled = _rounded_rect_photo(_CTRL_BTN_W, _CTRL_BTN_H, self._disabled_bg, _CTRL_BTN_R)
        use_rounded = self._img_normal is not None
        show_disabled = initial_state == tk.DISABLED
        init_bg = self._disabled_bg if show_disabled else bg
        if use_rounded:
            self._btn = tk.Button(
                self, text=text, font=(FONT_FAMILY, 11), fg=fg,
                image=self._img_disabled if show_disabled else self._img_normal,
                compound='center',
                bg=init_bg,
                activebackground=init_bg, activeforeground=fg,
                highlightbackground=init_bg, highlightcolor=init_bg,
                relief='flat', bd=0, highlightthickness=0, padx=0, pady=0,
                cursor='hand2', command=command, state=initial_state,
                disabledforeground=FG_DISABLED, takefocus=0,
            )
        else:
            self._btn = tk.Button(
                self, text=text, font=(FONT_FAMILY, 12), fg=fg,
                bg=init_bg,
                activebackground=init_bg, activeforeground=fg,
                highlightbackground=init_bg, highlightcolor=init_bg,
                relief='flat', padx=18, pady=3, cursor='hand2',
                command=command, state=initial_state,
                disabledforeground=FG_DISABLED, takefocus=0,
            )
        self._use_rounded = use_rounded
        self._btn.pack()
        self._btn.bind('<Enter>', self._on_enter)
        self._btn.bind('<Leave>', self._on_leave)

    def _current_image(self):
        if self._btn['state'] == 'disabled':
            return self._img_disabled
        return self._img_normal

    def _apply_bg(self, color):
        """Set bg and matching border/active colors so no visible border mismatch."""
        self._btn.configure(
            bg=color, activebackground=color,
            highlightbackground=color, highlightcolor=color,
        )

    def _on_enter(self, e):
        if self._btn['state'] == 'normal':
            self._apply_bg(self._hover_bg)
            if self._use_rounded:
                self._btn.configure(image=self._img_hover)
        else:
            self._apply_bg(self._disabled_bg)
            if self._use_rounded:
                self._btn.configure(image=self._img_disabled)

    def _on_leave(self, e):
        color = self._disabled_bg if self._btn['state'] == 'disabled' else self._bg
        self._apply_bg(color)
        if self._use_rounded:
            self._btn.configure(image=self._current_image())

    def config(self, **kwargs):
        if 'state' in kwargs:
            self._btn.config(state=kwargs['state'])
        if 'bg' in kwargs:
            self._bg = kwargs['bg']
            self._apply_bg(self._bg)
        if self._use_rounded and ('state' in kwargs or 'bg' in kwargs):
            self._btn.configure(image=self._current_image())
        if 'state' in kwargs and kwargs['state'] == 'disabled':
            self._apply_bg(self._disabled_bg)

    def __getitem__(self, key):
        if key == 'state':
            return self._btn['state']
        raise KeyError(key)


class App:
    def __init__(self, root, borderless: bool = True):
        self.root = root
        self._borderless = borderless
        root.title('Where Songs Meet')
        root.attributes('-topmost', True)
        self.playing = False
        self._stop_buttons_enabled = False  # enable only when playback actually starts (first progress)

        BORDER_WIDTH = 5  # visible border around the app (root shows this color; content frame is inset)
        root.configure(bg=BORDER)
        root.minsize(360 + 2 * BORDER_WIDTH, 520 + 2 * BORDER_WIDTH)
        root.geometry(f'{450 + 2 * BORDER_WIDTH}x{640 + 2 * BORDER_WIDTH}')
        root.option_add('*Font', LABEL_FONT)
        root.option_add('*Background', BG)
        root.option_add('*Foreground', FG)
        root.option_add('*selectBackground', ACCENT)
        root.option_add('*selectForeground', BG)

        # ttk styles (clam for full control)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background=BG)
        style.configure(
            'TNotebook.Tab',
            background=TAB_BG_UNSELECTED, foreground=FG, padding=[SMALL_PAD, 2]
        )
        style.map(
            'TNotebook.Tab',
            background=[('selected', CARD)],
            padding=[('selected', [PAD, 2])],
        )
        style.configure(
            'Playback.Horizontal.TProgressbar',
            troughcolor=SUBTLE,
            background=ACCENT,
            darkcolor=ACCENT,
            lightcolor=ACCENT,
            bordercolor=BORDER,
        )
        style.configure(
            'TCombobox',
            fieldbackground=ENTRY_BG,
            foreground=ENTRY_FG,
            background=SUBTLE,
            arrowcolor=FG,
        )
        style.map('TCombobox', fieldbackground=[('readonly', ENTRY_BG)])

        self.folder_path = ''
        self.tempo = tk.DoubleVar(value=1.0)
        self.transpose = tk.IntVar(value=0)
        # Repeat options and current playback source
        self.repeat_file = tk.BooleanVar(value=False)
        self.repeat_os = tk.BooleanVar(value=False)
        self.repeat_playlist = tk.BooleanVar(value=False)
        self.save_file_var = tk.BooleanVar(value=False)
        self.save_os_var = tk.BooleanVar(value=False)
        self._current_source: str | None = None
        self._stopped_by_user: bool = False
        self._playlist = Playlist()
        self._room = Room()
        self._sync_temp_paths: list[str] = []
        self._sync_my_reported_label = ''  # label we sent via report_playing (client)
        self._sync_last_players: list = []  # last room_playing list (for client UI refresh)
        self._sync_last_participant_count: int = -1  # host: previous client count (for "someone joined" feedback)
        self._focus_check_after_id: str | None = None  # stop playback when foreground window is not the game
        # Last selection per tab (so Play together shows it even after switching tabs)
        self._last_file_path: str | None = None
        self._last_os_sid: str | None = None
        self._last_os_title: str | None = None
        self._last_tab_visited: str = 'file'  # 'file' or 'os'
        self._os_last_instruments: dict[str, set[int]] = {}  # sid -> last selected instrument ids (in-memory only)
        self._os_last_sync_assignments: dict[str, list[set[int]]] = {}  # sid -> [host_set, p1_set, p2_set, ...] per participant
        self._file_last_tracks: dict[str, set[int]] = {}  # path -> last selected track indices (in-memory only)

        self._song_settings = SongSettings()
        self._os_favorites = OsFavorites(self._song_settings.settings_dir)

        def _tooltip(btn, status_widget, hint: str):
            btn.bind('<Enter>', lambda e: status_widget.config(text=hint))
            btn.bind('<Leave>', lambda e: status_widget.config(text=''))

        self._icon_images = {}
        self._icon_images_small = {}
        self._icon_images_large = {}
        try:
            from src.icon_images import ICON_SIZE, ICON_SIZE_SMALL, ICON_SIZE_LARGE, get_all_theme_icons
            self._icon_images = get_all_theme_icons(ICON_SIZE)
            self._icon_size = ICON_SIZE
            self._icon_images_small = get_all_theme_icons(ICON_SIZE_SMALL)
            self._icon_size_small = ICON_SIZE_SMALL
            self._icon_images_large = get_all_theme_icons(ICON_SIZE_LARGE)
            self._icon_size_large = ICON_SIZE_LARGE
        except Exception:
            self._icon_size = 22
            self._icon_size_small = 18
            self._icon_size_large = 28

        def _icon_btn_kwargs(icon_key: str, small: bool = False, large: bool = False, **overrides):
            key_to_char = {
                'ADD_LIST': ICON_ADD_LIST, 'ADD_TO_PLAYLIST': ICON_ADD_TO_PLAYLIST,
                'BROWSER': ICON_BROWSER, 'CLEAR': ICON_CLEAR, 'CONNECT': ICON_CONNECT,
                'DISCONNECT': ICON_DISCONNECT, 'DOWNLOAD': ICON_DOWNLOAD,
                'FAV': ICON_FAV, 'FAV_OFF': ICON_FAV_OFF, 'FOLDER': ICON_FOLDER,
                'HOST': ICON_HOST, 'PLAY': ICON_PLAY, 'RELOAD': ICON_RELOAD,
                'REMOVE': ICON_REMOVE, 'SAVE': ICON_SAVE, 'SEARCH': ICON_SEARCH,
            'STOP': ICON_STOP, 'STOP_HOST': ICON_STOP_HOST,
            'UPDATE': ICON_UPDATE, 'LOG': ICON_LOG,
        }
            base = dict(
                bg=CARD, fg=FG, activebackground=CARD, activeforeground=FG,
                relief='flat', padx=BTN_PAD[0], pady=BTN_PAD[1], cursor='hand2',
            )
            if large:
                icon_set = self._icon_images_large
                size = self._icon_size_large
                base['padx'] = BTN_PAD_LARGE[0]
                base['pady'] = BTN_PAD_LARGE[1]
            elif small:
                icon_set = self._icon_images_small
                size = self._icon_size_small
            else:
                icon_set = self._icon_images
                size = self._icon_size
            img = icon_set.get(icon_key)
            if img:
                base['image'] = img
                base['text'] = ''
                base['width'] = size
                base['height'] = size
                # Generous padding so icon isn't clipped at 1080p (vs 4K)
                base['padx'] = 10
                base['pady'] = 6
            else:
                base['text'] = key_to_char.get(icon_key, '')
                base['font'] = ICON_FONT
                base['width'] = ICON_BTN_WIDTH if not small else 2
                base['height'] = 2 if not large else 2  # keep icon buttons same height when text fallback
                base['padx'] = ICON_BTN_PADX  # avoid icon cut off on left/right at low res
                # CONNECT (Join) and LOG need extra room at 1080p so they don't clip
                if icon_key in ('CONNECT', 'LOG'):
                    base['padx'] = 10
                    base['pady'] = 6
                    base['width'] = 8
            base.update(overrides)
            return base

        content = tk.Frame(root, bg=BG)
        content.pack(fill='both', expand=True, padx=BORDER_WIDTH, pady=BORDER_WIDTH)
        header = tk.Frame(content, bg=BG)
        header.pack(fill='x', padx=PAD, pady=(PAD, 2))
        title_label = tk.Label(header, text='Where Songs Meet', font=TITLE_FONT, fg=ACCENT, bg=BG)
        title_label.pack(side='left', anchor='w')
        version_label = tk.Label(header, text=f'  v{APP_VERSION}', font=SMALL_FONT, fg=SUBTLE, bg=BG)
        version_label.pack(side='left', anchor='w')
        header_btns = tk.Frame(header, bg=BG)
        header_btns.pack(side='right')
        if borderless:
            close_btn = tk.Button(
                header_btns, text='\u2715', command=root.quit,
                font=('Segoe UI', 12), fg=FG, bg=BG, activebackground=STOP_RED, activeforeground=FG,
                relief='flat', cursor='hand2', padx=4, pady=0
            )
            close_btn.pack(side='right', padx=(0, 2))
            close_btn.bind('<Enter>', lambda e: close_btn.configure(bg=STOP_RED))
            close_btn.bind('<Leave>', lambda e: close_btn.configure(bg=BG))
        self._log_btn = tk.Button(
            header_btns, command=self._open_log,
            **_icon_btn_kwargs('LOG', bg=BG, activebackground=BG)
        )
        self._log_btn.pack(side='right')
        self._update_btn = tk.Button(
            header_btns, command=self._check_for_updates,
            **_icon_btn_kwargs('UPDATE', bg=BG, activebackground=BG)
        )
        self._update_btn.pack(side='right')
        self._update_btn.bind('<Enter>', lambda e: self._update_btn.configure(bg=ACCENT))
        self._update_btn.bind('<Leave>', lambda e: self._update_btn.configure(bg=BG))

        # Notebook: File tab + Online Sequencer tab
        self.notebook = ttk.Notebook(content)
        self.notebook.pack(fill='both', expand=True, padx=PAD, pady=(0, SMALL_PAD))

        # ---- Tab 1: File ----
        file_tab = tk.Frame(self.notebook, bg=CARD)
        self.notebook.add(file_tab, text='  File  ')

        # File section: folder + list of .mid files
        file_frame = tk.LabelFrame(
            file_tab, text='  File  ', font=LABEL_FONT,
            fg=SUBTLE, bg=CARD, labelanchor='n'
        )
        file_frame.pack(fill='both', expand=True, padx=PAD, pady=(0, SMALL_PAD))
        file_inner = tk.Frame(file_frame, bg=CARD)
        file_inner.pack(fill='both', expand=True, padx=PAD, pady=(2, SMALL_PAD))
        tk.Label(file_inner, text='Folder', font=LABEL_FONT, fg=FG, bg=CARD).grid(
            row=0, column=0, sticky='w', pady=(0, SMALL_PAD))
        self.folder_label = tk.Label(
            file_inner, text='No folder selected', font=SMALL_FONT,
            fg=SUBTLE, bg=CARD, anchor='w'
        )
        self.folder_label.grid(row=1, column=0, sticky='ew', padx=(0, 8))
        file_inner.columnconfigure(0, weight=1)
        open_folder_btn = tk.Button(
            file_inner, command=self.open_folder,
            **_icon_btn_kwargs('FOLDER')
        )
        open_folder_btn.grid(row=1, column=1, sticky='e')
        open_folder_btn.bind('<Enter>', lambda e: open_folder_btn.configure(bg=ACCENT))
        open_folder_btn.bind('<Leave>', lambda e: open_folder_btn.configure(bg=CARD))
        tk.Label(file_inner, text='MIDI file', font=LABEL_FONT, fg=FG, bg=CARD).grid(
            row=2, column=0, sticky='w', pady=(PAD, SMALL_PAD))
        add_to_playlist_file_btn = tk.Button(
            file_inner, command=self._add_file_to_playlist,
            **_icon_btn_kwargs('ADD_TO_PLAYLIST', small=True)
        )
        add_to_playlist_file_btn.grid(row=2, column=1, sticky='e')
        add_to_playlist_file_btn.bind('<Enter>', lambda e: add_to_playlist_file_btn.configure(bg=ACCENT))
        add_to_playlist_file_btn.bind('<Leave>', lambda e: add_to_playlist_file_btn.configure(bg=CARD))
        list_frame = tk.Frame(file_inner, bg=CARD)
        list_frame.grid(row=3, column=0, columnspan=2, sticky='nsew', pady=(0, SMALL_PAD))
        file_inner.rowconfigure(3, weight=1)
        scrollbar = tk.Scrollbar(list_frame, bg=SUBTLE)
        scrollbar.pack(side='right', fill='y')
        self.file_listbox = tk.Listbox(
            list_frame, height=LISTBOX_MIN_ROWS, font=LABEL_FONT,
            bg=ENTRY_BG, fg=ENTRY_FG, selectbackground=ACCENT, selectforeground=BG,
            relief='flat', highlightthickness=0, yscrollcommand=scrollbar.set,
            selectmode=tk.EXTENDED
        )
        self.file_listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind('<<ListboxSelect>>', lambda e: self._on_file_selection_changed())

        # Options section (sliders for tempo and transpose)
        opts_frame = tk.LabelFrame(
            file_tab, text='  Options  ', font=LABEL_FONT,
            fg=SUBTLE, bg=CARD, labelanchor='n'
        )
        opts_frame.pack(fill='x', padx=PAD, pady=(0, SMALL_PAD))
        opts_inner = tk.Frame(opts_frame, bg=CARD)
        opts_inner.pack(fill='x', padx=PAD, pady=(2, SMALL_PAD))
        scale_opts = {'font': LABEL_FONT, 'fg': FG, 'bg': CARD, 'troughcolor': ENTRY_BG, 'activebackground': CARD, 'highlightthickness': 0}
        # Tempo row (top) — label column fixed width so bars align
        tk.Label(opts_inner, text='Tempo ×', font=LABEL_FONT, fg=FG, bg=CARD, width=10, anchor='w').grid(
            row=0, column=0, sticky='sw', padx=(0, 4))
        tempo_row = tk.Frame(opts_inner, bg=CARD)
        tempo_row.grid(row=0, column=1, sticky='ew', padx=(0, PAD))
        opts_inner.columnconfigure(1, weight=1)
        self._tempo_scale = tk.Scale(
            tempo_row, from_=0.25, to=1.75, resolution=0.05, orient='horizontal',
            variable=self.tempo, length=200, **scale_opts
        )
        self._tempo_scale.pack(side='left', fill='x', expand=True)

        def _resize_tempo_scale(e):
            w = max(60, e.width)
            if w != self._tempo_scale.cget('length'):
                self._tempo_scale.config(length=w)
        tempo_row.bind('<Configure>', _resize_tempo_scale)
        # Transpose row (below) — same label width so bar aligns with tempo
        tk.Label(opts_inner, text='Transpose', font=LABEL_FONT, fg=FG, bg=CARD, width=10, anchor='w').grid(
            row=1, column=0, sticky='sw', padx=(0, 4), pady=(SMALL_PAD, 0))
        transpose_row = tk.Frame(opts_inner, bg=CARD)
        transpose_row.grid(row=1, column=1, sticky='ew', padx=(0, PAD), pady=(SMALL_PAD, 0))
        self._transpose_scale = tk.Scale(
            transpose_row, from_=-12, to=12, resolution=1, orient='horizontal',
            variable=self.transpose, length=200, **scale_opts
        )
        self._transpose_scale.pack(side='left', fill='x', expand=True)

        def _resize_transpose_scale(e):
            w = max(60, e.width)
            if w != self._transpose_scale.cget('length'):
                self._transpose_scale.config(length=w)
        transpose_row.bind('<Configure>', _resize_transpose_scale)

        # Set initial scale lengths once (update_idletasks then direct call — no after_idle to avoid "invalid command name" when packaged)
        root.update_idletasks()
        self._apply_file_scale_sizes()

        # Save tempo/transpose for this song (File tab)
        def _on_save_file_cb():
            key = self._get_file_song_key()
            if self.save_file_var.get():
                if not key:
                    self.save_file_var.set(False)
                    messagebox.showwarning('No selection', 'Select a MIDI file first.')
                    return
                self._song_settings.set(key, self.tempo.get(), self.transpose.get())
                self.status.config(text='Tempo/transpose saved for this song.')
            else:
                if key:
                    self._song_settings.delete(key)
        save_file_cb = tk.Checkbutton(
            opts_inner, text='Save for this song', variable=self.save_file_var,
            font=SMALL_FONT, fg=FG, bg=CARD, activeforeground=FG, activebackground=CARD,
            selectcolor=ENTRY_BG, cursor='hand2', command=_on_save_file_cb
        )
        save_file_cb.grid(row=2, column=0, sticky='w', pady=(SMALL_PAD, 0))

        # Actions
        actions = tk.Frame(file_tab, bg=CARD)
        actions.pack(fill='x', padx=PAD, pady=(0, 6))
        self.play_btn = ControlButton(
            actions, kind='play', bg=PLAY_GREEN, hover_bg=PLAY_GREEN_HOVER, fg=BG,
            command=self.play, initial_state=tk.NORMAL
        )
        self.play_btn.grid(row=0, column=0, padx=(0, CTRL_BTN_GAP))
        self.stop_btn = ControlButton(
            actions, kind='stop', bg=STOP_RED, hover_bg=STOP_RED_HOVER, fg=BG,
            command=self.stop, initial_state=tk.DISABLED, disabled_bg=SUBTLE
        )
        self.stop_btn.grid(row=0, column=1, padx=(0, CTRL_BTN_GAP))
        actions.columnconfigure(2, weight=1)
        repeat_file_btn = tk.Checkbutton(
            actions, text='Repeat', variable=self.repeat_file,
            font=LABEL_FONT, fg=FG, bg=CARD,
            activeforeground=FG, activebackground=CARD,
            selectcolor=ENTRY_BG, cursor='hand2'
        )
        repeat_file_btn.grid(row=0, column=3, sticky='e')

        # Progress bar (shown during playback)
        self.progress_frame = tk.Frame(file_tab, bg=CARD)
        self.progress_frame.pack(fill='x', padx=PAD, pady=(2, 0))
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, style='Playback.Horizontal.TProgressbar',
            mode='determinate', maximum=100, value=0
        )
        self.progress_bar.pack(fill='x')

        # Status
        status_frame = tk.Frame(file_tab, bg=CARD)
        status_frame.pack(fill='x', padx=PAD, pady=(2, PAD))
        self.status = tk.Label(
            status_frame,
            text='Ready — focus the game window before playing',
            font=SMALL_FONT, fg=SUBTLE, bg=CARD
        )
        self.status.pack(anchor='w')
        _tooltip(open_folder_btn, self.status, 'Open folder')
        _tooltip(self._log_btn, self.status, 'Open log file')
        _tooltip(self._update_btn, self.status, 'Check for updates')
        _tooltip(add_to_playlist_file_btn, self.status, 'Add to playlist')
        _tooltip(save_file_cb, self.status, 'Save tempo/transpose for this song')
        _tooltip(self.play_btn, self.status, 'Play')
        _tooltip(self.stop_btn, self.status, 'Stop (Escape from any window)')

        # ---- Tab 2: Online Sequencer ----
        os_tab = tk.Frame(self.notebook, bg=CARD)
        self.notebook.add(os_tab, text='  Online Sequencer  ')
        os_sequences_frame = tk.LabelFrame(
            os_tab, text='  Sequences  ', font=LABEL_FONT,
            fg=SUBTLE, bg=CARD, labelanchor='n'
        )
        os_sequences_frame.pack(fill='both', expand=True, padx=PAD, pady=(0, SMALL_PAD))
        os_inner = tk.Frame(os_sequences_frame, bg=CARD)
        os_inner.pack(fill='both', expand=True, padx=PAD, pady=(2, SMALL_PAD))
        tk.Label(os_inner, text='Sequences (onlinesequencer.net)', font=LABEL_FONT, fg=FG, bg=CARD).pack(anchor='w')
        os_toolbar = tk.Frame(os_inner, bg=CARD)
        os_toolbar.pack(fill='x', pady=(2, SMALL_PAD))
        tk.Label(os_toolbar, text='Sort:', font=LABEL_FONT, fg=FG, bg=CARD, width=7, anchor='w').grid(row=0, column=0, padx=(0, 6), sticky='w')
        self.os_sort_menu = ttk.Combobox(
            os_toolbar,
            values=[label for _, label in SORT_OPTIONS],
            state='readonly', width=18, font=LABEL_FONT
        )
        self.os_sort_menu.grid(row=0, column=1, padx=(0, 8), sticky='ew')
        os_toolbar.columnconfigure(1, weight=1)
        load_btn = tk.Button(
            os_toolbar, command=self._load_sequences,
            **_icon_btn_kwargs('RELOAD')
        )
        load_btn.grid(row=0, column=2, padx=(0, 0))
        load_btn.bind('<Enter>', lambda e: load_btn.configure(bg=ACCENT))
        load_btn.bind('<Leave>', lambda e: load_btn.configure(bg=CARD))
        self.os_sort_menu.set('Newest')
        self.os_sequences: list[tuple[str, str]] = []
        os_search_frame = tk.Frame(os_inner, bg=CARD)
        os_search_frame.pack(fill='x', pady=(0, SMALL_PAD))
        tk.Label(os_search_frame, text='Search:', font=LABEL_FONT, fg=FG, bg=CARD, width=7, anchor='w').grid(
            row=0, column=0, padx=(0, 6), sticky='w'
        )
        self.os_search_var = tk.StringVar()
        os_search_entry = tk.Entry(
            os_search_frame,
            textvariable=self.os_search_var,
            font=LABEL_FONT,
            bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
            relief='flat', highlightthickness=0, width=18
        )
        os_search_entry.grid(row=0, column=1, padx=(0, 8), sticky='ew')
        os_search_frame.columnconfigure(1, weight=1)
        os_search_btn = tk.Button(
            os_search_frame, command=self._search_sequences,
            **_icon_btn_kwargs('SEARCH')
        )
        os_search_btn.grid(row=0, column=2, sticky='e')
        os_search_btn.bind('<Enter>', lambda e: os_search_btn.configure(bg=ACCENT))
        os_search_btn.bind('<Leave>', lambda e: os_search_btn.configure(bg=CARD))
        os_search_entry.bind('<Return>', lambda e: self._search_sequences())
        os_icon_row = tk.Frame(os_inner, bg=CARD)
        os_icon_row.pack(fill='x', pady=(0, SMALL_PAD))
        # Pack order: last packed = leftmost. So pack Open first (rightmost), then Download, Add playlist, Unfav, Fav (leftmost).
        os_open_btn = tk.Button(
            os_icon_row, command=self._open_selected_sequence,
            **_icon_btn_kwargs('BROWSER', small=True)
        )
        os_open_btn.pack(side='right', padx=(BTN_GAP, 0))
        os_open_btn.bind('<Enter>', lambda e: os_open_btn.configure(bg=ACCENT))
        os_open_btn.bind('<Leave>', lambda e: os_open_btn.configure(bg=CARD))
        os_download_btn = tk.Button(
            os_icon_row, command=self._download_os_midi,
            **_icon_btn_kwargs('DOWNLOAD', small=True)
        )
        os_download_btn.pack(side='right', padx=(BTN_GAP, 0))
        os_download_btn.bind('<Enter>', lambda e: os_download_btn.configure(bg=ACCENT))
        os_download_btn.bind('<Leave>', lambda e: os_download_btn.configure(bg=CARD))
        os_add_playlist_btn = tk.Button(
            os_icon_row, command=self._add_os_to_playlist,
            **_icon_btn_kwargs('ADD_TO_PLAYLIST', small=True)
        )
        os_add_playlist_btn.pack(side='right', padx=(BTN_GAP, 0))
        os_add_playlist_btn.bind('<Enter>', lambda e: os_add_playlist_btn.configure(bg=ACCENT))
        os_add_playlist_btn.bind('<Leave>', lambda e: os_add_playlist_btn.configure(bg=CARD))
        os_unfav_btn = tk.Button(
            os_icon_row, command=self._os_remove_from_favorites,
            **_icon_btn_kwargs('FAV_OFF', small=True)
        )
        os_unfav_btn.pack(side='right', padx=(BTN_GAP, 0))
        os_unfav_btn.bind('<Enter>', lambda e: os_unfav_btn.configure(bg=ACCENT))
        os_unfav_btn.bind('<Leave>', lambda e: os_unfav_btn.configure(bg=CARD))
        os_fav_btn = tk.Button(
            os_icon_row, command=self._os_add_to_favorites,
            **_icon_btn_kwargs('FAV', small=True)
        )
        os_fav_btn.pack(side='right', padx=(BTN_GAP, 0))
        os_fav_btn.bind('<Enter>', lambda e: os_fav_btn.configure(bg=ACCENT))
        os_fav_btn.bind('<Leave>', lambda e: os_fav_btn.configure(bg=CARD))
        os_list_frame = tk.Frame(os_inner, bg=CARD)
        os_list_frame.pack(fill='both', expand=True, pady=(0, SMALL_PAD))
        os_scroll = tk.Scrollbar(os_list_frame, bg=SUBTLE)
        os_scroll.pack(side='right', fill='y')
        self.os_listbox = tk.Listbox(
            os_list_frame, font=LABEL_FONT, height=OS_LISTBOX_MIN_ROWS,
            bg=ENTRY_BG, fg=ENTRY_FG, selectbackground=ACCENT, selectforeground=BG,
            relief='flat', highlightthickness=0, yscrollcommand=os_scroll.set,
            selectmode=tk.EXTENDED
        )
        self.os_listbox.pack(side='left', fill='both', expand=True)
        self.os_listbox.bind('<Double-Button-1>', lambda e: self._open_selected_sequence())
        self.os_listbox.bind('<<ListboxSelect>>', lambda e: self._on_os_selection_changed())
        os_scroll.config(command=self.os_listbox.yview)
        # Show saved favorites in list immediately if any
        if self._os_favorites.list_all():
            self.os_sequences = list(self._os_favorites.list_all())
            self._refresh_os_listbox()
            self.os_listbox.selection_set(0)
            self.os_listbox.see(0)
        # Info below list: status, progress bar
        os_info_frame = tk.Frame(os_inner, bg=CARD)
        os_info_frame.pack(fill='x', pady=(2, 0))
        self.os_status = tk.Label(
            os_info_frame,
            text='Choose sort and click Load list to show sequences.',
            font=SMALL_FONT, fg=SUBTLE, bg=CARD
        )
        self.os_status.pack(anchor='w')
        if self._os_favorites.list_all():
            self.os_status.config(text=f'★ {len(self._os_favorites.list_all())} favorites. Load list for more.')
        _tooltip(load_btn, self.os_status, 'Load list')
        _tooltip(os_open_btn, self.os_status, 'Open selected in browser')
        _tooltip(os_download_btn, self.os_status, 'Download MIDI')
        _tooltip(os_fav_btn, self.os_status, 'Add to favorites')
        _tooltip(os_unfav_btn, self.os_status, 'Remove from favorites')
        _tooltip(os_add_playlist_btn, self.os_status, 'Add to playlist')
        _tooltip(os_search_btn, self.os_status, 'Search')
        # Options (same as File tab: tempo and transpose sliders, shared vars)
        os_opts_frame = tk.LabelFrame(
            os_tab, text='  Options  ', font=LABEL_FONT,
            fg=SUBTLE, bg=CARD, labelanchor='n'
        )
        os_opts_frame.pack(fill='x', padx=PAD, pady=(0, SMALL_PAD))
        os_opts_inner = tk.Frame(os_opts_frame, bg=CARD)
        os_opts_inner.pack(fill='x', padx=PAD, pady=(2, SMALL_PAD))
        os_scale_opts = {'font': LABEL_FONT, 'fg': FG, 'bg': CARD, 'troughcolor': ENTRY_BG, 'activebackground': CARD, 'highlightthickness': 0}
        # Tempo row (top) — label column fixed width so bars align
        tk.Label(os_opts_inner, text='Tempo ×', font=LABEL_FONT, fg=FG, bg=CARD, width=10, anchor='w').grid(
            row=0, column=0, sticky='sw', padx=(0, 4))
        os_tempo_row = tk.Frame(os_opts_inner, bg=CARD)
        os_tempo_row.grid(row=0, column=1, sticky='ew', padx=(0, PAD))
        os_opts_inner.columnconfigure(1, weight=1)
        self._os_tempo_scale = tk.Scale(
            os_tempo_row, from_=0.25, to=1.75, resolution=0.05, orient='horizontal',
            variable=self.tempo, length=200, **os_scale_opts
        )
        self._os_tempo_scale.pack(side='left', fill='x', expand=True)

        def _os_resize_tempo_scale(e):
            w = max(60, e.width)
            if w != self._os_tempo_scale.cget('length'):
                self._os_tempo_scale.config(length=w)
        os_tempo_row.bind('<Configure>', _os_resize_tempo_scale)
        # Transpose row (below) — same label width so bar aligns with tempo
        tk.Label(os_opts_inner, text='Transpose', font=LABEL_FONT, fg=FG, bg=CARD, width=10, anchor='w').grid(
            row=1, column=0, sticky='sw', padx=(0, 4), pady=(SMALL_PAD, 0))
        os_transpose_row = tk.Frame(os_opts_inner, bg=CARD)
        os_transpose_row.grid(row=1, column=1, sticky='ew', padx=(0, PAD), pady=(SMALL_PAD, 0))
        self._os_transpose_scale = tk.Scale(
            os_transpose_row, from_=-12, to=12, resolution=1, orient='horizontal',
            variable=self.transpose, length=200, **os_scale_opts
        )
        self._os_transpose_scale.pack(side='left', fill='x', expand=True)

        def _os_resize_transpose_scale(e):
            w = max(60, e.width)
            if w != self._os_transpose_scale.cget('length'):
                self._os_transpose_scale.config(length=w)
        os_transpose_row.bind('<Configure>', _os_resize_transpose_scale)
        # Save tempo/transpose for this song (OS tab)
        def _on_save_os_cb():
            key = self._get_os_song_key()
            if self.save_os_var.get():
                if not key:
                    self.save_os_var.set(False)
                    messagebox.showwarning('No selection', 'Select a sequence first.')
                    return
                self._song_settings.set(key, self.tempo.get(), self.transpose.get())
                self.os_status.config(text='Tempo/transpose saved for this song.')
            else:
                if key:
                    self._song_settings.delete(key)
        save_os_cb = tk.Checkbutton(
            os_opts_inner, text='Save for this song', variable=self.save_os_var,
            font=SMALL_FONT, fg=FG, bg=CARD, activeforeground=FG, activebackground=CARD,
            selectcolor=ENTRY_BG, cursor='hand2', command=_on_save_os_cb
        )
        save_os_cb.grid(row=2, column=0, sticky='w', pady=(SMALL_PAD, 0))
        _tooltip(save_os_cb, self.os_status, 'Save tempo/transpose for this song')

        # OS tab: actions (Play, Stop), progress bar (same style as File tab)
        self._os_last_midi_path: str | None = None
        os_actions = tk.Frame(os_tab, bg=CARD)
        os_actions.pack(fill='x', padx=PAD, pady=(SMALL_PAD, 6))
        self.os_play_btn = ControlButton(
            os_actions, kind='play', bg=PLAY_GREEN, hover_bg=PLAY_GREEN_HOVER, fg=BG,
            command=self._load_and_play_sequence, initial_state=tk.NORMAL
        )
        self.os_play_btn.grid(row=0, column=0, padx=(0, CTRL_BTN_GAP))
        self.os_stop_btn = ControlButton(
            os_actions, kind='stop', bg=STOP_RED, hover_bg=STOP_RED_HOVER, fg=BG,
            command=self.stop, initial_state=tk.DISABLED, disabled_bg=SUBTLE
        )
        self.os_stop_btn.grid(row=0, column=1, padx=(0, CTRL_BTN_GAP))
        os_actions.columnconfigure(2, weight=1)
        _tooltip(self.os_play_btn, self.os_status, 'Play')
        _tooltip(self.os_stop_btn, self.os_status, 'Stop (Escape from any window)')
        repeat_os_btn = tk.Checkbutton(
            os_actions, text='Repeat', variable=self.repeat_os,
            font=LABEL_FONT, fg=FG, bg=CARD,
            activeforeground=FG, activebackground=CARD,
            selectcolor=ENTRY_BG, cursor='hand2'
        )
        repeat_os_btn.grid(row=0, column=3, sticky='e')
        # Progress bar (below actions, like File tab)
        self.os_progress_frame = tk.Frame(os_tab, bg=CARD)
        self.os_progress_frame.pack(fill='x', padx=PAD, pady=(2, 0))
        self.os_progress_bar = ttk.Progressbar(
            self.os_progress_frame, style='Playback.Horizontal.TProgressbar',
            mode='determinate', maximum=100, value=0
        )
        self.os_progress_bar.pack(fill='x')
        # Bottom: only "Ready — focus..." message
        os_ready_frame = tk.Frame(os_tab, bg=CARD)
        os_ready_frame.pack(fill='x', padx=PAD, pady=(2, PAD))
        tk.Label(
            os_ready_frame,
            text='Ready — focus the game window before playing',
            font=SMALL_FONT, fg=SUBTLE, bg=CARD
        ).pack(anchor='w')

        # ---- Tab 3: Playlist ----
        playlist_tab = tk.Frame(self.notebook, bg=CARD)
        self.notebook.add(playlist_tab, text='  Playlist  ')
        pl_frame = tk.LabelFrame(
            playlist_tab, text='  Playlist  ', font=LABEL_FONT,
            fg=SUBTLE, bg=CARD, labelanchor='n'
        )
        pl_frame.pack(fill='both', expand=True, padx=PAD, pady=(0, SMALL_PAD))
        pl_inner = tk.Frame(pl_frame, bg=CARD)
        pl_inner.pack(fill='both', expand=True, padx=PAD, pady=(2, SMALL_PAD))
        tk.Label(pl_inner, text='Songs play in order.\nAdd from File or Online Sequencer tab.', font=LABEL_FONT, fg=FG, bg=CARD, justify='left').pack(anchor='w')
        pl_toolbar = tk.Frame(pl_inner, bg=CARD)
        pl_toolbar.pack(fill='x', pady=(2, SMALL_PAD))
        # Toolbar: only Remove and Clear (right-aligned). Play/Stop go in pl_actions below.
        # Pack order: last packed = leftmost. Pack Clear first (rightmost), then Remove.
        pl_clear_btn = tk.Button(
            pl_toolbar, command=self._clear_playlist,
            **_icon_btn_kwargs('CLEAR', small=True)
        )
        pl_clear_btn.pack(side='right', padx=(BTN_GAP, 0))
        pl_clear_btn.bind('<Enter>', lambda e: pl_clear_btn.configure(bg=ACCENT))
        pl_clear_btn.bind('<Leave>', lambda e: pl_clear_btn.configure(bg=CARD))
        pl_remove_btn = tk.Button(
            pl_toolbar, command=self._remove_from_playlist,
            **_icon_btn_kwargs('REMOVE', small=True)
        )
        pl_remove_btn.pack(side='right', padx=(BTN_GAP, 0))
        pl_remove_btn.bind('<Enter>', lambda e: pl_remove_btn.configure(bg=ACCENT))
        pl_remove_btn.bind('<Leave>', lambda e: pl_remove_btn.configure(bg=CARD))
        pl_list_frame = tk.Frame(pl_inner, bg=CARD)
        pl_list_frame.pack(fill='both', expand=True, pady=(0, SMALL_PAD))
        pl_scroll = tk.Scrollbar(pl_list_frame, bg=SUBTLE)
        pl_scroll.pack(side='right', fill='y')
        self.playlist_listbox = tk.Listbox(
            pl_list_frame, font=LABEL_FONT, height=OS_LISTBOX_MIN_ROWS,
            bg=ENTRY_BG, fg=ENTRY_FG, selectbackground=ACCENT, selectforeground=BG,
            relief='flat', highlightthickness=0, yscrollcommand=pl_scroll.set,
            selectmode=tk.EXTENDED
        )
        self.playlist_listbox.pack(side='left', fill='both', expand=True)
        pl_scroll.config(command=self.playlist_listbox.yview)
        # Play/Stop row at bottom of tab (like File and OS tabs)
        pl_actions = tk.Frame(playlist_tab, bg=CARD)
        pl_actions.pack(fill='x', padx=PAD, pady=(SMALL_PAD, 6))
        pl_actions.columnconfigure(2, weight=1)
        self.pl_play_btn = ControlButton(
            pl_actions, kind='play', bg=PLAY_GREEN, hover_bg=PLAY_GREEN_HOVER, fg=BG,
            command=self._play_playlist, initial_state=tk.NORMAL
        )
        self.pl_play_btn.grid(row=0, column=0, padx=(0, CTRL_BTN_GAP))
        self.pl_stop_btn = ControlButton(
            pl_actions, kind='stop', bg=STOP_RED, hover_bg=STOP_RED_HOVER, fg=BG,
            command=self.stop, initial_state=tk.DISABLED, disabled_bg=SUBTLE
        )
        self.pl_stop_btn.grid(row=0, column=1, padx=(0, CTRL_BTN_GAP))
        repeat_pl_btn = tk.Checkbutton(
            pl_actions, text='Repeat', variable=self.repeat_playlist,
            font=LABEL_FONT, fg=FG, bg=CARD,
            activeforeground=FG, activebackground=CARD,
            selectcolor=ENTRY_BG, cursor='hand2'
        )
        repeat_pl_btn.grid(row=0, column=3, sticky='e')
        # Progress bar (same as File / OS tabs)
        self.pl_progress_frame = tk.Frame(playlist_tab, bg=CARD)
        self.pl_progress_frame.pack(fill='x', padx=PAD, pady=(2, 0))
        self.pl_progress_bar = ttk.Progressbar(
            self.pl_progress_frame, style='Playback.Horizontal.TProgressbar',
            mode='determinate', maximum=100, value=0
        )
        self.pl_progress_bar.pack(fill='x')
        # Status (same style as other tabs)
        pl_status_frame = tk.Frame(playlist_tab, bg=CARD)
        pl_status_frame.pack(fill='x', padx=PAD, pady=(2, PAD))
        self.pl_status = tk.Label(
            pl_status_frame,
            text='Ready — focus the game window before playing',
            font=SMALL_FONT, fg=SUBTLE, bg=CARD
        )
        self.pl_status.pack(anchor='w')
        _tooltip(pl_remove_btn, self.pl_status, 'Remove selected')
        _tooltip(pl_clear_btn, self.pl_status, 'Clear playlist')
        _tooltip(self.pl_play_btn, self.pl_status, 'Play playlist')
        _tooltip(self.pl_stop_btn, self.pl_status, 'Stop (Escape from any window)')
        _tooltip(repeat_pl_btn, self.pl_status, 'When finished, play playlist again from the beginning')

        # ---- Tab 4: Play together ----
        sync_tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(sync_tab, text='  Play together  ')
        # Scrollable area so Join block is not cut off on low resolutions
        sync_canvas = tk.Canvas(sync_tab, bg=BG, highlightthickness=0)
        sync_scroll = tk.Scrollbar(sync_tab, orient='vertical', command=sync_canvas.yview)
        sync_scroll.pack(side='right', fill='y')
        sync_canvas.pack(side='left', fill='both', expand=True)
        sync_canvas.configure(yscrollcommand=sync_scroll.set)
        sync_frame = tk.Frame(sync_canvas, bg=BG)
        sync_canvas_window = sync_canvas.create_window((0, 0), window=sync_frame, anchor='nw')
        def _sync_on_frame_configure(e):
            sync_canvas.configure(scrollregion=sync_canvas.bbox('all'))
            sync_canvas.itemconfig(sync_canvas_window, width=e.width)
        sync_frame.bind('<Configure>', _sync_on_frame_configure)
        def _sync_on_canvas_configure(e):
            sync_canvas.itemconfig(sync_canvas_window, width=e.width)
        sync_canvas.bind('<Configure>', _sync_on_canvas_configure)
        def _sync_mousewheel(e):
            sync_canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units')
        sync_canvas.bind('<MouseWheel>', _sync_mousewheel)
        sync_frame.pack(fill='x', padx=PAD, pady=(0, PAD))
        # Intro
        sync_intro = tk.Label(
            sync_frame,
            text='Host or join a room — when the host presses Play, everyone starts together.',
            font=LABEL_FONT, fg=FG, bg=BG, justify='left', wraplength=320
        )
        sync_intro.pack(anchor='w', pady=(PAD, PAD))
        # Host block
        host_card = tk.Frame(sync_frame, bg=CARD, highlightbackground=CARD_BORDER, highlightthickness=1)
        host_card.pack(fill='x', pady=(0, SMALL_PAD))
        host_inner = tk.Frame(host_card, bg=CARD)
        host_inner.pack(fill='x', padx=PAD, pady=PAD)
        host_row1 = tk.Frame(host_inner, bg=CARD)
        host_row1.pack(fill='x')
        tk.Label(host_row1, text='Host', font=LABEL_FONT, fg=FG, bg=CARD, width=6, anchor='w').pack(side='left', padx=(0, BTN_GAP))
        self.sync_host_var = tk.StringVar(value=f'{get_lan_ip()}:{DEFAULT_PORT}')
        sync_host_entry = tk.Entry(
            host_row1, textvariable=self.sync_host_var, width=22,
            font=LABEL_FONT, bg=ENTRY_BG, fg=ENTRY_FG, relief='flat', highlightthickness=0
        )
        sync_host_entry.pack(side='left', fill='x', expand=True, padx=(0, BTN_GAP))
        host_btns = tk.Frame(host_inner, bg=CARD)
        host_btns.pack(fill='x', pady=(SMALL_PAD, 0))
        self.sync_host_btn = tk.Button(
            host_btns, command=self._sync_start_host,
            **_icon_btn_kwargs('HOST')
        )
        self.sync_host_btn.pack(side='left', padx=(0, BTN_GAP))
        self.sync_host_btn.bind('<Enter>', lambda e: self.sync_host_btn.configure(bg=ACCENT))
        self.sync_host_btn.bind('<Leave>', lambda e: self.sync_host_btn.configure(bg=CARD))
        self.sync_stop_host_btn = tk.Button(
            host_btns, command=self._sync_stop_host, state='disabled',
            **_icon_btn_kwargs('STOP_HOST')
        )
        self.sync_stop_host_btn.pack(side='left', padx=(0, BTN_GAP))
        self.sync_stop_host_btn.bind('<Enter>', lambda e: self.sync_stop_host_btn.configure(bg=ACCENT))
        self.sync_stop_host_btn.bind('<Leave>', lambda e: self.sync_stop_host_btn.configure(bg=CARD))
        self.sync_host_status = tk.Label(
            host_btns, text='', font=SMALL_FONT, fg=SUBTLE, bg=CARD
        )
        self.sync_host_status.pack(side='left', padx=(PAD, 0))
        sync_host_tooltip = tk.Label(host_btns, text='', font=SMALL_FONT, fg=SUBTLE, bg=CARD)
        sync_host_tooltip.pack(side='left', padx=(PAD, 0))
        self.sync_firewall_hint = tk.Label(
            host_inner,
            text='If others can\'t connect: allow this app in Windows Firewall (Private).',
            font=HINT_FONT, fg=SUBTLE, bg=CARD, justify='left', wraplength=300
        )
        self.sync_firewall_hint.pack(anchor='w', pady=(SMALL_PAD, 0))
        # Public link (tunnel) — label on first line, buttons/status on second line
        tunnel_row = tk.Frame(host_inner, bg=CARD)
        tunnel_row.pack(fill='x', pady=(SMALL_PAD, 0))
        tk.Label(tunnel_row, text='Public link', font=LABEL_FONT, fg=FG, bg=CARD, anchor='w').pack(anchor='w')
        tunnel_btns = tk.Frame(tunnel_row, bg=CARD)
        tunnel_btns.pack(fill='x')
        self.sync_create_tunnel_btn = tk.Button(
            tunnel_btns, text='Create public link', command=self._sync_create_tunnel,
            font=LABEL_FONT, fg=FG, bg=ENTRY_BG, activebackground=ACCENT, activeforeground=FG,
            relief='flat', cursor='hand2', padx=BTN_PAD[0], pady=2
        )
        self.sync_create_tunnel_btn.pack(side='left', padx=(0, BTN_GAP))
        self.sync_tunnel_addr_var = tk.StringVar(value='')
        self.sync_tunnel_addr_label = tk.Label(
            tunnel_btns, textvariable=self.sync_tunnel_addr_var,
            font=LABEL_FONT, fg=ACCENT, bg=CARD
        )
        self.sync_tunnel_addr_label.pack(side='left', padx=(0, BTN_GAP))
        self.sync_tunnel_copy_btn = tk.Button(
            tunnel_btns, text='Copy', command=self._sync_copy_tunnel_addr,
            font=LABEL_FONT, fg=FG, bg=ENTRY_BG, activebackground=ACCENT, activeforeground=FG,
            relief='flat', cursor='hand2', padx=BTN_PAD[0], pady=2
        )
        self.sync_tunnel_copy_btn.pack(side='left', padx=(0, BTN_GAP))
        self.sync_tunnel_status = tk.Label(
            tunnel_btns, text='', font=HINT_FONT, fg=SUBTLE, bg=CARD
        )
        self.sync_tunnel_status.pack(side='left', padx=(PAD, 0))
        self._sync_update_tunnel_ui()
        # Join block
        join_card = tk.Frame(sync_frame, bg=CARD, highlightbackground=CARD_BORDER, highlightthickness=1)
        join_card.pack(fill='x', pady=(SMALL_PAD, 0))
        join_inner = tk.Frame(join_card, bg=CARD)
        join_inner.pack(fill='x', padx=PAD, pady=PAD)
        join_row1 = tk.Frame(join_inner, bg=CARD)
        join_row1.pack(fill='x')
        tk.Label(join_row1, text='Join', font=LABEL_FONT, fg=FG, bg=CARD, width=6, anchor='w').pack(side='left', padx=(0, BTN_GAP))
        self.sync_join_var = tk.StringVar(value='')
        sync_join_entry = tk.Entry(
            join_row1, textvariable=self.sync_join_var, width=16,
            font=LABEL_FONT, bg=ENTRY_BG, fg=ENTRY_FG, relief='flat', highlightthickness=0
        )
        sync_join_entry.pack(side='left', fill='x', expand=True, padx=(0, BTN_GAP))
        join_hint = tk.Label(
            join_inner, text='e.g. 192.168.0.1:38472 or host\'s public link (e.g. 0.tcp.ngrok.io:12345)',
            font=HINT_FONT, fg=SUBTLE, bg=CARD, wraplength=320
        )
        join_hint.pack(anchor='w', pady=(2, SMALL_PAD))
        join_btns = tk.Frame(join_inner, bg=CARD)
        join_btns.pack(fill='x')
        self.sync_join_btn = tk.Button(
            join_btns, command=self._sync_join,
            **_icon_btn_kwargs('CONNECT')
        )
        self.sync_join_btn.pack(side='left', padx=(0, BTN_GAP))
        self.sync_join_btn.bind('<Enter>', lambda e: self.sync_join_btn.configure(bg=ACCENT))
        self.sync_join_btn.bind('<Leave>', lambda e: self.sync_join_btn.configure(bg=CARD))
        self.sync_disconnect_btn = tk.Button(
            join_btns, command=self._sync_disconnect, state='disabled',
            **_icon_btn_kwargs('DISCONNECT')
        )
        self.sync_disconnect_btn.pack(side='left', padx=(0, BTN_GAP))
        self.sync_disconnect_btn.bind('<Enter>', lambda e: self.sync_disconnect_btn.configure(bg=ACCENT))
        self.sync_disconnect_btn.bind('<Leave>', lambda e: self.sync_disconnect_btn.configure(bg=CARD))
        self.sync_status = tk.Label(
            join_inner, text='Not connected.',
            font=SMALL_FONT, fg=SUBTLE, bg=CARD
        )
        self.sync_status.pack(anchor='w', pady=(SMALL_PAD, 0))
        _tooltip(self.sync_host_btn, sync_host_tooltip, 'Start hosting')
        _tooltip(self.sync_stop_host_btn, sync_host_tooltip, 'Stop hosting')
        _tooltip(self.sync_join_btn, self.sync_status, 'Connect')
        _tooltip(self.sync_disconnect_btn, self.sync_status, 'Disconnect')
        # Latency test on its own row (avoids hover tooltip fighting with status text)
        self.sync_latency_row = tk.Frame(join_inner, bg=CARD)
        self.sync_test_latency_btn = tk.Button(
            self.sync_latency_row, text='Test latency', command=self._sync_test_latency,
            font=SMALL_FONT, fg=FG, bg=CARD, activebackground=CARD, activeforeground=FG,
            relief='flat', cursor='hand2'
        )
        self.sync_test_latency_btn.pack(side='left', padx=(0, BTN_GAP))
        self.sync_test_latency_btn.bind('<Enter>', lambda e: self.sync_test_latency_btn.configure(bg=ACCENT))
        self.sync_test_latency_btn.bind('<Leave>', lambda e: self.sync_test_latency_btn.configure(bg=CARD))
        self.sync_latency_label = tk.Label(
            self.sync_latency_row, text='', font=SMALL_FONT, fg=ACCENT, bg=CARD
        )
        self.sync_latency_label.pack(side='left', padx=(0, BTN_GAP))
        self.sync_latency_hint = tk.Label(
            self.sync_latency_row, text='', font=SMALL_FONT, fg=SUBTLE, bg=CARD
        )
        self.sync_latency_hint.pack(side='left')
        _tooltip(self.sync_test_latency_btn, self.sync_latency_hint, 'Measure round-trip time to host.')
        _tooltip(self.sync_latency_label, self.sync_latency_hint, 'Round-trip time to host. Higher latency may need a longer countdown before play.')
        self.sync_latency_row.pack_forget()  # show only when client connected
        # Client option: play own selection at same time as host
        self.sync_play_my_selection = tk.BooleanVar(value=False)
        sync_options = tk.Frame(sync_frame, bg=BG)
        sync_options.pack(fill='x', pady=(SMALL_PAD, 0))
        self.sync_play_my_cb = tk.Checkbutton(
            sync_options, text='Play my selection instead of host\'s (start at same time)',
            variable=self.sync_play_my_selection, font=SMALL_FONT, fg=FG, bg=BG,
            activeforeground=FG, activebackground=BG, selectcolor=CARD, cursor='hand2',
            command=self._sync_report_selection
        )
        self.sync_play_my_cb.pack(anchor='w')
        # Per-machine timing offset: adjust when this device actually starts (ms, negative = earlier, positive = later)
        self._sync_offset_max_ms = 1000
        self.sync_offset_ms = tk.IntVar(value=0)
        offset_row = tk.Frame(sync_options, bg=BG)
        offset_row.pack(fill='x', pady=(SMALL_PAD, 0))
        tk.Label(
            offset_row, text='Adjust my timing (ms):',
            font=SMALL_FONT, fg=SUBTLE, bg=BG
        ).pack(side='left')
        self.sync_offset_scale = tk.Scale(
            offset_row, from_=-self._sync_offset_max_ms, to=self._sync_offset_max_ms, orient='horizontal',
            variable=self.sync_offset_ms, resolution=25, length=200,
            showvalue=False, bg=BG, fg=FG, troughcolor=CARD,
            highlightthickness=0, bd=0
        )
        self.sync_offset_scale.pack(side='left', padx=(SMALL_PAD, 0))
        self._sync_offset_entry = tk.Entry(
            offset_row, width=5, font=SMALL_FONT, bg=ENTRY_BG, fg=ENTRY_FG,
            justify='right', relief='flat', highlightthickness=0
        )
        self._sync_offset_entry.insert(0, '0')
        self._sync_offset_entry.pack(side='left', padx=(SMALL_PAD, 0))
        def _sync_offset_scale_changed(*_):
            try:
                self._sync_offset_entry.delete(0, tk.END)
                self._sync_offset_entry.insert(0, str(self.sync_offset_ms.get()))
            except tk.TclError:
                pass
        def _sync_offset_entry_apply(*_):
            try:
                s = self._sync_offset_entry.get().strip()
                v = int(s) if s else 0
                v = max(-self._sync_offset_max_ms, min(self._sync_offset_max_ms, v))
                self.sync_offset_ms.set(v)
                self._sync_offset_entry.delete(0, tk.END)
                self._sync_offset_entry.insert(0, str(v))
            except ValueError:
                _sync_offset_scale_changed()
        self.sync_offset_ms.trace_add('write', _sync_offset_scale_changed)
        self._sync_offset_entry.bind('<Return>', _sync_offset_entry_apply)
        self._sync_offset_entry.bind('<FocusOut>', _sync_offset_entry_apply)
        # Your current selection (always visible, updated when you change file/OS)
        self.sync_your_selection_label = tk.Label(
            sync_frame, text='Your selection: (none)', font=SMALL_FONT, fg=SUBTLE, bg=BG,
            justify='left', wraplength=320
        )
        self.sync_your_selection_label.pack(anchor='w', pady=(SMALL_PAD, 0))
        # Who is playing what (host + clients) when connected
        self.sync_now_playing_label = tk.Label(
            sync_frame, text='', font=SMALL_FONT, fg=SUBTLE, bg=BG,
            justify='left', wraplength=320
        )
        self.sync_now_playing_label.pack(anchor='w', pady=(SMALL_PAD, 0))
        # Refresh "Your selection" when user switches to Play together tab
        def _on_notebook_tab_changed(_event):
            try:
                if self.notebook.index(self.notebook.select()) == 3:  # Play together
                    self._sync_update_your_selection_label()
            except (tk.TclError, ValueError):
                pass
        self.notebook.bind('<<NotebookTabChanged>>', _on_notebook_tab_changed)
        self._sync_register_room_callbacks()
        self._start_stop_hotkey_listener()

        if borderless:
            root.update_idletasks()
            self._header_drag_start: tuple[int, int, int, int] | None = None
            def _on_header_press(e):
                self._header_drag_start = (e.x_root, e.y_root, root.winfo_x(), root.winfo_y())
            def _on_header_drag(e):
                if self._header_drag_start is None:
                    return
                dx = e.x_root - self._header_drag_start[0]
                dy = e.y_root - self._header_drag_start[1]
                root.geometry(f'+{self._header_drag_start[2] + dx}+{self._header_drag_start[3] + dy}')
            def _on_header_release(_e):
                self._header_drag_start = None
            for w in (header, title_label, version_label):
                w.bind('<Button-1>', _on_header_press)
                w.bind('<B1-Motion>', _on_header_drag)
                w.bind('<ButtonRelease-1>', _on_header_release)
                w.configure(cursor='fleur')
            root.overrideredirect(True)

    def _sync_register_room_callbacks(self):
        """Register room callbacks; all run via root.after on main thread."""
        def on_clients_changed(n: int):
            log.debug("Room participants: %s", n)
            self.root.after(0, lambda: self._sync_update_host_status(n))
        def on_connected():
            log.info("Room callback: connected")
            # Request multiple sync samples so clock offset is more stable before first Play
            for i in range(5):
                self.root.after(i * 150, self._room.send_sync_request)
            self.root.after(0, self._sync_update_joined_ui)
        def on_disconnected():
            log.info("Room callback: disconnected")
            self.root.after(0, self._sync_update_disconnected_ui)
        def on_play_file(start_in: float, midi_bytes: bytes, tempo: float, transpose: int, host_send_time: float | None = None, host_playing_label: str = '', client_recv_time: float | None = None, sync_offset: float | None = None):
            self.root.after(0, lambda: self._sync_received_play_file(start_in, midi_bytes, tempo, transpose, host_send_time, host_playing_label, client_recv_time, sync_offset))
        def on_play_os(start_in: float, sid: str, tempo: float, transpose: int, host_send_time: float | None = None, host_playing_label: str = '', client_recv_time: float | None = None, sync_offset: float | None = None, assigned_instrument_ids: set[int] | None = None):
            self.root.after(0, lambda: self._sync_received_play_os(start_in, sid, tempo, transpose, host_send_time, host_playing_label, client_recv_time, sync_offset, assigned_instrument_ids))
        def on_sync_ack(offset: float):
            self.root.after(0, lambda: None)  # offset already stored in Room; optional UI feedback
        def on_pong(rtt_sec: float):
            self.root.after(0, lambda: self._sync_on_pong(rtt_sec))
        def on_stop():
            self.root.after(0, self.stop)
        def on_room_playing(players: list):
            self.root.after(0, lambda: self._sync_update_now_playing(players))
        self._room.on_clients_changed = on_clients_changed
        self._room.on_connected = on_connected
        self._room.on_disconnected = on_disconnected
        self._room.on_play_file = on_play_file
        self._room.on_play_os = on_play_os
        self._room.on_sync_ack = on_sync_ack
        self._room.on_pong = on_pong
        self._room.on_stop = on_stop
        self._room.on_room_playing = on_room_playing

    def _start_stop_hotkey_listener(self):
        """Start a global keyboard listener: Escape stops playback from any window."""
        if not playback.KEYBOARD_AVAILABLE:
            return
        try:
            from pynput.keyboard import Listener as KListener, Key as KKey
        except ImportError:
            return

        def on_press(key):
            try:
                if key == KKey.esc:
                    self.root.after(0, self.stop)
            except (tk.TclError, RuntimeError):
                pass

        listener = KListener(on_press=on_press)
        listener.start()
        self._stop_hotkey_listener = listener

    def _open_log(self):
        """Open the log file with the default system application."""
        path = getattr(_log_config, 'LOG_FILE_PATH', None)
        if not path or not os.path.isfile(path):
            messagebox.showinfo('Log', 'Log file is not available.')
            return
        try:
            if os.name == 'nt':
                os.startfile(path)
            else:
                subprocess.run(['xdg-open', path], check=False)
        except OSError as e:
            messagebox.showerror('Log', f'Could not open log: {e}')

    def _check_for_updates(self):
        """Run update check in a background thread and show result on main thread."""
        self._update_btn.config(state='disabled')
        if hasattr(self, 'status'):
            self.status.config(text='Checking for updates…')

        def do_check():
            try:
                result = check_for_updates()
            except Exception as e:
                result = (None, None, None, None, str(e))
            self.root.after(0, lambda: self._on_update_check_done(result))

        threading.Thread(target=do_check, daemon=True).start()

    def _on_update_check_done(self, result):
        latest_version, html_url, body, download_url, error_detail = result
        self._update_btn.config(state='normal')
        if hasattr(self, 'status'):
            self.status.config(text='Ready — focus the game window before playing')
        if latest_version is None:
            msg = error_detail or 'Could not check for updates. Check your connection.'
            log.warning("Update check failed: %s", msg)
            messagebox.showerror('Update check failed', msg)
            return
        if not is_newer(latest_version):
            messagebox.showinfo('Up to date', f'You have the latest version (v{APP_VERSION}).')
            return
        self._show_update_dialog(latest_version, html_url, body, download_url)

    def _show_update_dialog(self, latest_version: str, html_url: str, body: str | None, download_url: str | None):
        top = tk.Toplevel(self.root)
        top.title('Update available')
        top.configure(bg=BG)
        top.transient(self.root)
        top.grab_set()
        frame = tk.Frame(top, bg=BG, padx=PAD, pady=PAD)
        frame.pack(fill='both', expand=True)
        tk.Label(
            frame,
            text=f'Version {latest_version} is available (you have v{APP_VERSION}).',
            font=LABEL_FONT, fg=FG, bg=BG, wraplength=320,
        ).pack(anchor='w')
        if body:
            notes = tk.Text(
                frame, height=6, wrap='word', font=SMALL_FONT,
                fg=FG, bg=CARD, relief='flat', padx=4, pady=4,
            )
            notes.pack(fill='both', expand=True, pady=(SMALL_PAD, 0))
            notes.insert('1.0', body[:1000] + ('…' if len(body) > 1000 else ''))
            notes.config(state='disabled')
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill='x', pady=(PAD, 0))
        btn_style = dict(
            font=LABEL_FONT, bg=SUBTLE, fg=FG,
            activebackground=ACCENT, activeforeground=FG,
            relief='flat', padx=BTN_PAD[0], pady=BTN_PAD[1], cursor='hand2',
        )

        def open_page():
            open_release_page(html_url)

        tk.Button(btn_frame, text='Open release page', command=open_page, **btn_style).pack(side='left', padx=(0, BTN_GAP))
        if download_url:

            def download_and_run():
                save_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                path, err = download_update(download_url, save_dir=save_dir)
                if path:
                    try:
                        # Run from extracted folder (zip) or single exe; only replace-in-place for single exe when frozen
                        from_zip = os.path.basename(os.path.dirname(path)) == "where-songs-meet"
                        if os.name == "nt" and getattr(sys, "frozen", False) and not from_zip:
                            current_exe = sys.executable
                            exe_dir = os.path.dirname(current_exe)
                            def q(s: str) -> str:
                                return s.replace('"', '""')
                            # Run the downloaded exe; use start /wait so the batch waits for it to exit, then copy and delete (one exe left).
                            batch = f'''@echo off
set "ME=%~f0"
timeout /t 4 /nobreak >nul
start "" /wait /D "{q(exe_dir)}" "{q(path)}"
copy /Y "{q(path)}" "{q(current_exe)}"
del "{q(path)}"
del "%ME%"
'''
                            fd, batch_path = tempfile.mkstemp(suffix='.bat', text=True)
                            try:
                                os.write(fd, batch.encode('utf-8'))
                                os.close(fd)
                                subprocess.Popen(
                                    ['cmd', '/c', batch_path],
                                    creationflags=subprocess.CREATE_NO_WINDOW,
                                )
                            except Exception:
                                os.close(fd)
                                os.unlink(batch_path)
                                raise
                        else:
                            if os.name == "nt":
                                os.startfile(path)
                            else:
                                subprocess.run(["xdg-open", path], check=False)
                        top.destroy()
                        self.root.quit()
                    except Exception:
                        messagebox.showinfo('Downloaded', f'Saved to: {path}')
                        top.destroy()
                else:
                    msg = err or 'Could not download the update.'
                    log.warning("Update download failed: %s", msg)
                    messagebox.showerror('Download failed', msg)

            tk.Button(btn_frame, text='Download and run', command=download_and_run, **btn_style).pack(side='left', padx=(0, BTN_GAP))
        tk.Button(btn_frame, text='Close', command=top.destroy, **btn_style).pack(side='left')

    def _sync_play_join_sound(self):
        """Play a short sound when someone joins (host) or when client connects. No-op if unavailable."""
        try:
            if os.name == 'nt':
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

    def _sync_update_host_status(self, n: int):
        if not self._room.is_host():
            return
        addr = get_lan_ip()
        s = self.sync_host_var.get().strip()
        port = s.rsplit(':', 1)[-1] if ':' in s else str(DEFAULT_PORT)
        self.sync_host_var.set(f'{addr}:{port}')
        # Feedback when someone joins
        if self._sync_last_participant_count >= 0 and n > self._sync_last_participant_count:
            self.sync_host_status.config(text=f'  —  Someone joined! ({n} participant(s))')
            self._sync_play_join_sound()
        else:
            self.sync_host_status.config(text=f'  —  {n} participant(s)')
        self._sync_last_participant_count = n
        if self._room.is_host():
            self._sync_report_selection()  # broadcast so new clients see host selection

    def _sync_start_host(self):
        s = self.sync_host_var.get().strip()
        if ':' not in s:
            messagebox.showwarning('Invalid address', 'Enter IP:port (e.g. 192.168.1.5:38472)')
            return
        try:
            port = int(s.rsplit(':', 1)[1].strip())
        except ValueError:
            messagebox.showwarning('Invalid port', 'Enter a number for the port.')
            return
        if port <= 0 or port > 65535:
            messagebox.showwarning('Invalid port', 'Port must be between 1 and 65535.')
            return
        log.info("Starting host on port %s", port)
        # Host needs firewall rule too so clients can connect inbound
        if messagebox.askyesno(
            "Firewall",
            "Allow Where Songs Meet through Windows Firewall for private and public networks?\n\n"
            "Required so others can connect to your room.",
            icon="question",
        ):
            ok, msg = add_firewall_rules()
            if not ok:
                log.warning("Firewall rules failed: %s", msg)
                messagebox.showwarning("Firewall", f"Could not add firewall rules: {msg}")
            else:
                log.info("Firewall rules added: %s", msg)
                self.sync_host_status.config(text='  —  ' + msg)
        actual = self._room.start_host(port)
        if actual == 0:
            log.error("Host failed: could not bind port %s (in use or blocked)", port)
            messagebox.showerror('Host failed', 'Could not start the room (port in use or blocked by firewall?).')
            return
        log.info("Host started on port %s", actual)
        addr = get_lan_ip()
        self.sync_host_var.set(f'{addr}:{actual}')
        self.sync_host_btn.config(state='disabled')
        self.sync_stop_host_btn.config(state='normal')
        self.sync_join_btn.config(state='disabled')
        self.sync_disconnect_btn.config(state='disabled')  # only for client
        self.sync_status.config(text='You are the host. Select music and press Play — others will follow.')
        self.sync_play_my_cb.pack_forget()  # hide "play my selection" when host
        self._sync_report_selection()  # show initial selection (or "(select a song)")
        self._sync_last_participant_count = 0
        self._sync_update_host_status(0)
        self._sync_update_tunnel_ui()

    def _sync_stop_host(self):
        log.info("Stopping host")
        self._room.stop_host()
        self._sync_last_participant_count = -1
        self.sync_host_var.set(f'{get_lan_ip()}:{DEFAULT_PORT}')
        self.sync_host_btn.config(state='normal')
        self.sync_stop_host_btn.config(state='disabled')
        self.sync_join_btn.config(state='normal')
        self.sync_host_status.config(text='')
        self.sync_firewall_hint.pack(anchor='w', pady=(SMALL_PAD, 0))
        self.sync_play_my_cb.pack(anchor='w')
        self.sync_status.config(text='Not connected.')
        self._sync_update_now_playing([])
        if is_tunnel_active():
            stop_tunnel()
        self._sync_update_tunnel_ui()

    def _sync_create_tunnel(self):
        """Create public link via ngrok TCP tunnel (runs in thread)."""
        if not self._room.is_host():
            return
        s = self.sync_host_var.get().strip()
        if ':' not in s:
            return
        try:
            port = int(s.rsplit(':', 1)[1].strip())
        except ValueError:
            return
        self.sync_create_tunnel_btn.config(state='disabled')
        self.sync_tunnel_status.config(text='Creating tunnel…')

        def do_start():
            ok, addr, err = start_tcp_tunnel(port)
            self.root.after(0, lambda: self._sync_on_tunnel_created(ok, addr, err))

        threading.Thread(target=do_start, daemon=True).start()

    def _sync_on_tunnel_created(self, ok: bool, addr: str, err: str):
        self.sync_create_tunnel_btn.config(state='normal' if self._room.is_host() else 'disabled')
        if ok:
            self.sync_tunnel_addr_var.set(addr)
            self.sync_tunnel_status.config(text='Friends can join at this address.')
            self._sync_update_tunnel_ui()
        else:
            self.sync_tunnel_status.config(text=err or 'Tunnel failed.')
            self._sync_update_tunnel_ui()

    def _sync_copy_tunnel_addr(self):
        addr = get_public_addr()
        if not addr:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(addr)
        self.sync_tunnel_status.config(text='Copied to clipboard.')
        self.root.after(2000, lambda: self._sync_update_tunnel_ui())

    def _sync_update_tunnel_ui(self):
        """Show/hide Create public link vs tunnel address + Copy/Close based on state."""
        hosting = self._room.is_host()
        active = is_tunnel_active()
        if active:
            self.sync_tunnel_addr_var.set(get_public_addr() or '')
            self.sync_tunnel_addr_label.pack(side='left', padx=(0, BTN_GAP))
            self.sync_tunnel_copy_btn.pack(side='left', padx=(0, BTN_GAP))
            self.sync_create_tunnel_btn.pack_forget()
            self.sync_tunnel_status.config(text='Friends can join at this address.')
        else:
            self.sync_create_tunnel_btn.pack(side='left', padx=(0, BTN_GAP))
            self.sync_tunnel_addr_label.pack_forget()
            self.sync_tunnel_copy_btn.pack_forget()
            self.sync_create_tunnel_btn.config(state='normal' if hosting else 'disabled')
            if hosting:
                ok, reason = is_available()
                self.sync_tunnel_status.config(text=reason if not ok else 'Share this with friends outside your network.')
            else:
                self.sync_tunnel_status.config(text='Start hosting first.')

    def _sync_join(self):
        # Ask to allow the app through the firewall (private and public) for joining/hosting
        if messagebox.askyesno(
            "Firewall",
            "Allow Where Songs Meet through Windows Firewall for private and public networks?\n\n"
            "This helps when joining or hosting rooms.",
            icon="question",
        ):
            ok, msg = add_firewall_rules()
            if not ok:
                log.warning("Firewall rules failed (join): %s", msg)
                messagebox.showwarning("Firewall", f"Could not add firewall rules: {msg}")
            else:
                log.info("Firewall rules added (join): %s", msg)
                self.sync_status.config(text=msg)

        s = self.sync_join_var.get().strip()
        if ':' not in s:
            messagebox.showwarning('Invalid address', 'Enter host:port (e.g. 192.168.1.10:38472)')
            return
        host, port_str = s.rsplit(':', 1)
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showwarning('Invalid port', 'Enter a number for the port.')
            return
        log.info("Joining %s:%s", host.strip(), port)
        if not self._room.connect(host.strip(), port):
            log.warning("Connect failed to %s:%s", host.strip(), port)
            messagebox.showerror('Connect failed', 'Could not connect to the host.')
            return
        log.info("Connected to host %s:%s", host.strip(), port)
        self.sync_join_btn.config(state='disabled')
        self.sync_disconnect_btn.config(state='normal')
        self.sync_host_btn.config(state='disabled')
        self.sync_status.config(text='Connected. Waiting for host to play.')

    def _sync_update_joined_ui(self):
        self.sync_join_btn.config(state='disabled')
        self.sync_disconnect_btn.config(state='normal')
        self.sync_host_btn.config(state='disabled')
        self.sync_play_my_cb.pack(anchor='w')  # show when client
        self.sync_status.config(text='Connected to host! Waiting for host to play.')
        self._sync_play_join_sound()
        if hasattr(self, 'sync_latency_label'):
            self.sync_latency_label.config(text='')
        if hasattr(self, 'sync_latency_row'):
            self.sync_latency_row.pack(fill='x', pady=(SMALL_PAD, 0))
        self._sync_report_selection()  # report our selection so host sees us (or "(host's selection)")

    def _sync_test_latency(self):
        """Client: send ping to host; when pong received, show RTT in sync_latency_label."""
        if not self._room.is_client():
            return
        if hasattr(self, 'sync_latency_label'):
            self.sync_latency_label.config(text='…')
        self._room.send_ping()

    def _sync_on_pong(self, rtt_sec: float):
        """Called on main thread when host replied to our ping; show round-trip time."""
        if hasattr(self, 'sync_latency_label'):
            ms = max(0, round(rtt_sec * 1000))
            self.sync_latency_label.config(text=f'Latency: {ms} ms')

    def _sync_update_disconnected_ui(self):
        self.sync_join_btn.config(state='normal')
        self.sync_disconnect_btn.config(state='disabled')
        self.sync_host_btn.config(state='normal')
        self.sync_status.config(text='Disconnected.')
        self._sync_my_reported_label = ''
        if hasattr(self, 'sync_latency_row'):
            self.sync_latency_row.pack_forget()
        if hasattr(self, 'sync_latency_label'):
            self.sync_latency_label.config(text='')
        self._sync_update_now_playing([])

    def _sync_update_now_playing(self, players: list):
        """Update the 'Now playing' label from room_playing list [(who, label), ...]."""
        self._sync_last_players = list(players)
        if not players:
            self.sync_now_playing_label.config(text='')
            return
        lines = []
        if self._room.is_host():
            for i, (who, label) in enumerate(players):
                name = 'You' if who == 'host' else f'Client {i}'
                text = label.strip() or '(select a song)'
                lines.append(f'{name}: {text}')
        else:
            host_label = next((l for w, l in players if w == 'host'), '')
            lines.append(f"Host: {host_label.strip() or '(select a song)'}")
            you_label = self._sync_my_reported_label or "(host's selection)"
            lines.append(f"You: {you_label}")
        self.sync_now_playing_label.config(text='\n'.join(lines))

    def _get_selected_os(self) -> tuple[str | None, str | None]:
        """Return (sid, title) for selected OS sequence, or (None, None)."""
        sel = self.os_listbox.curselection()
        if not sel or not self.os_sequences:
            return None, None
        idx = sel[0]
        if idx >= len(self.os_sequences):
            return None, None
        return self.os_sequences[idx]

    def _get_sync_selection_label(self) -> str:
        """Return label for current selection (file or OS), or last tab's selection when listbox is empty (e.g. after tab switch)."""
        path = self.get_selected_file()
        if path:
            return os.path.basename(path)
        sid, title = self._get_selected_os()
        if sid:
            return f"OS: {title}" if title else f"OS: {sid}"
        # Use stored selection from last tab when current listbox has no selection
        if self._last_tab_visited == 'file' and self._last_file_path:
            return os.path.basename(self._last_file_path)
        if self._last_os_sid:
            return f"OS: {self._last_os_title}" if self._last_os_title else f"OS: {self._last_os_sid}"
        return ""

    def _sync_update_your_selection_label(self):
        """Update the 'Your selection:' line in Play together (call when file/OS selection changes)."""
        label = self._get_sync_selection_label()
        text = label if label else "(none)"
        self.sync_your_selection_label.config(text=f"Your selection: {text}")

    def _sync_report_selection(self):
        """Report current selection to the room so everyone sees it before Play."""
        if not self._room.is_connected():
            return
        if self._room.is_host():
            label = self._get_sync_selection_label() or "(select a song)"
            self._room.host_report_playing(label)
        else:
            if self.sync_play_my_selection.get():
                label = self._get_sync_selection_label() or "(select a song)"
            else:
                label = "(host's selection)"
            self._sync_my_reported_label = label
            self._room.send_report_playing(label)
            if self._sync_last_players:
                self._sync_update_now_playing(self._sync_last_players)

    def _sync_disconnect(self):
        if not self._room.is_client():
            return
        log.info("Disconnecting from room")
        self._room.disconnect()
        self.sync_join_btn.config(state='normal')
        self.sync_disconnect_btn.config(state='disabled')
        self.sync_host_btn.config(state='normal')
        self.sync_status.config(text='Disconnected.')

    def _sync_local_offset_sec(self) -> float:
        """Return local timing adjustment in seconds (slider)."""
        try:
            return (self.sync_offset_ms.get() or 0) / 1000.0
        except Exception:
            return 0.0

    def _sync_received_play_file(self, start_in_sec: float, midi_bytes: bytes, tempo: float, transpose: int, host_send_time: float | None = None, host_playing_label: str = '', client_recv_time: float | None = None, sync_offset: float | None = None):
        """Client received play_file: play host's file or own selection at same time; report what we're playing."""
        log.info("Client received play_file (start_in=%.1fs, %s bytes)", start_in_sec, len(midi_bytes))
        if not playback.KEYBOARD_AVAILABLE:
            return
        path = self.get_selected_file() or self._last_file_path
        use_my = self._room.is_client() and self.sync_play_my_selection.get() and path
        if use_my:
            my_label = os.path.basename(path)
            # Use client's own tempo and transposition when playing their selection
            tempo, transpose = self.tempo.get(), self.transpose.get()
        else:
            try:
                f = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
                f.write(midi_bytes)
                f.close()
                path = f.name
                self._sync_temp_paths.append(path)
            except OSError:
                return
            my_label = host_playing_label.strip() or "host's selection"
        # Use clock sync offset when available so we start at same moment as host; else fall back to receive-time delay
        if sync_offset is not None and host_send_time is not None and isinstance(host_send_time, (int, float)):
            start_at = (float(host_send_time) + start_in_sec) - sync_offset
        elif client_recv_time is not None and isinstance(client_recv_time, (int, float)):
            start_at = float(client_recv_time) + start_in_sec
        else:
            start_at = time.time() + start_in_sec
        # Apply local per-machine timing adjustment (slider) so user can fine-tune their start
        start_at += self._sync_local_offset_sec()
        self._sync_my_reported_label = my_label
        self._room.send_report_playing(my_label)

        def wait_then_play():
            delay = start_at - time.time()
            if delay > 0:
                time.sleep(delay)
            self.root.after(0, lambda: self._sync_start_file_playback(path, tempo, transpose))
        threading.Thread(target=wait_then_play, daemon=True).start()

    def _sync_start_file_playback(self, path: str, tempo: float, transpose: int, track_indices: set[int] | None = None):
        """Start playback from a path (sync received file); runs on main thread."""
        self._current_source = 'sync'
        self._stopped_by_user = False
        self.playing = True
        self.play_btn.config(state='disabled')
        self.os_play_btn.config(state='disabled')
        if hasattr(self, 'pl_play_btn'):
            self.pl_play_btn.config(state='disabled')
        # Stop buttons enabled in _set_progress when playback actually starts
        self.status.config(text='Playing… (synced)')
        self.os_status.config(text='Playing… (synced)')
        if hasattr(self, 'sync_status'):
            self.sync_status.config(text='Playing…')
        threading.Thread(
            target=self._play_thread,
            args=(path, tempo, transpose),
            kwargs={'track_indices': track_indices},
            daemon=True
        ).start()
        self._start_focus_check()

    def _sync_received_play_os(self, start_in_sec: float, sid: str, tempo: float, transpose: int, host_send_time: float | None = None, host_playing_label: str = '', client_recv_time: float | None = None, sync_offset: float | None = None, assigned_instrument_ids: set[int] | None = None):
        """Client received play_os: play host's OS (with assigned instruments) or own selection; report what we're playing."""
        log.info("Client received play_os sid=%s (start_in=%.1fs)", sid, start_in_sec)
        if not playback.KEYBOARD_AVAILABLE:
            return
        use_my = self._room.is_client() and self.sync_play_my_selection.get()
        my_sid, my_title = self._get_selected_os() if use_my else (None, None)
        if use_my and not my_sid:
            my_sid, my_title = self._last_os_sid, self._last_os_title
        use_my = use_my and bool(my_sid)
        if use_my:
            # Use client's own tempo and transposition when playing their selection
            tempo, transpose = self.tempo.get(), self.transpose.get()
            # When playing own selection: require client to have selected at least one instrument (in OS tab)
            my_inst = self._os_last_instruments.get(my_sid)
            if not my_inst or len(my_inst) == 0:
                self.root.after(0, lambda: messagebox.showwarning(
                    'No instruments selected',
                    'Select your sequence in the Online Sequencer tab, click Play, and choose at least one instrument. Then try again.',
                ))
                return
        # When playing host selection: require host to have sent instrument assignments (everyone has instruments)
        elif assigned_instrument_ids is None or len(assigned_instrument_ids) == 0:
            self.root.after(0, lambda: messagebox.showwarning('No instruments assigned', 'Host must assign you at least one instrument before playing.'))
            return
        # Use clock sync offset when available so we start at same moment as host; else fall back to receive-time delay
        if sync_offset is not None and host_send_time is not None and isinstance(host_send_time, (int, float)):
            start_at = (float(host_send_time) + start_in_sec) - sync_offset
        elif client_recv_time is not None and isinstance(client_recv_time, (int, float)):
            start_at = float(client_recv_time) + start_in_sec
        else:
            start_at = time.time() + start_in_sec
        # Apply local per-machine timing adjustment (slider) so user can fine-tune their start
        start_at += self._sync_local_offset_sec()
        my_label = f"OS: {my_title}" if (use_my and my_title) else (f"OS: {my_sid}" if use_my else (host_playing_label.strip() or "host's selection"))
        self._sync_my_reported_label = my_label
        self._room.send_report_playing(my_label)

        def download_and_schedule():
            if use_my:
                try:
                    my_inst = self._os_last_instruments.get(my_sid)
                    path = download_sequence_midi(my_sid, bpm=110, timeout=20, instrument_ids=my_inst)
                except Exception:
                    self.root.after(0, lambda: self.sync_status.config(text='Download failed.'))
                    return
            else:
                try:
                    binary = fetch_sequence_binary(sid, timeout=20)
                    path = sequence_binary_to_midi(binary, bpm=110, instrument_ids=assigned_instrument_ids)
                except Exception:
                    self.root.after(0, lambda: self.sync_status.config(text='Download failed.'))
                    return
            delay = start_at - time.time()
            if delay > 0:
                time.sleep(delay)
            self.root.after(0, lambda: self._sync_start_os_playback(path, tempo, transpose))
        threading.Thread(target=download_and_schedule, daemon=True).start()

    def _sync_start_os_playback(self, path: str, tempo: float, transpose: int):
        """Start playback from OS path (sync); runs on main thread."""
        self._os_last_midi_path = path
        self._current_source = 'sync'
        self._stopped_by_user = False
        self.playing = True
        self.play_btn.config(state='disabled')
        self.os_play_btn.config(state='disabled')
        if hasattr(self, 'pl_play_btn'):
            self.pl_play_btn.config(state='disabled')
        # Stop buttons enabled in _set_progress when playback actually starts
        self.status.config(text='Playing… (synced)')
        self.os_status.config(text='Playing… (synced)')
        if hasattr(self, 'sync_status'):
            self.sync_status.config(text='Playing…')
        self._os_playing_path = path
        threading.Thread(
            target=self._play_thread,
            args=(path, tempo, transpose),
            daemon=True
        ).start()
        self._start_focus_check()

    def _load_sequences(self):
        label = (self.os_sort_menu.get() or 'Newest').strip()
        sort = next((v for v, l in SORT_OPTIONS if l == label), '1')
        self.os_status.config(text='Loading…')
        self.os_listbox.delete(0, tk.END)
        self.os_sequences.clear()

        def do_fetch():
            try:
                pairs = fetch_sequences(sort=sort or '1')
                self.root.after(0, lambda: self._on_sequences_loaded(pairs, None))
            except Exception as e:
                self.root.after(0, lambda: self._on_sequences_loaded([], str(e)))

        threading.Thread(target=do_fetch, daemon=True).start()

    def _search_sequences(self):
        label = (self.os_sort_menu.get() or 'Newest').strip()
        sort = next((v for v, l in SORT_OPTIONS if l == label), '1')
        query = (self.os_search_var.get() or '').strip()
        self.os_status.config(text='Searching…' if query else 'Loading…')
        self.os_listbox.delete(0, tk.END)
        self.os_sequences.clear()

        def do_search():
            try:
                pairs = search_sequences(query=query, sort=sort or '1')
                self.root.after(0, lambda: self._on_sequences_loaded(pairs, None, from_search=bool(query)))
            except Exception as e:
                self.root.after(0, lambda: self._on_sequences_loaded([], str(e), from_search=False))

        threading.Thread(target=do_search, daemon=True).start()

    def _on_sequences_loaded(
        self, pairs: list[tuple[str, str]], error: str | None, *, from_search: bool = False
    ):
        self.os_sequences.clear()
        self.os_listbox.delete(0, tk.END)
        if error:
            self.os_status.config(text=f'Error: {error}')
            return
        fav_ids = self._os_favorites.fav_ids()
        # Favorites first, then results (excluding ids already in favorites to avoid duplicate)
        ordered: list[tuple[str, str]] = list(self._os_favorites.list_all())
        for sid, title in pairs:
            if sid not in fav_ids:
                ordered.append((sid, title))
        self.os_sequences = ordered
        for sid, title in self.os_sequences:
            self.os_listbox.insert(tk.END, self._os_display_line(sid, title))
        if self.os_sequences:
            self.os_listbox.selection_set(0)
            self.os_listbox.see(0)
        msg = f'{len(pairs)} sequences found.' if from_search else f'{len(pairs)} sequences loaded.'
        if self._os_favorites.list_all():
            msg += f'  ★ {len(self._os_favorites.list_all())} favorites at top.'
        self.os_status.config(text=msg)
        self._sync_update_your_selection_label()

    def _open_selected_sequence(self):
        sel = self.os_listbox.curselection()
        if not sel or not self.os_sequences:
            messagebox.showwarning('No selection', 'Load list and select a sequence first.')
            return
        idx = sel[0]
        if idx >= len(self.os_sequences):
            return
        sid, _ = self.os_sequences[idx]
        open_sequence(sid)
        self.os_status.config(text=f'Opened sequence {sid} in browser.')

    def _os_add_to_favorites(self):
        sel = self.os_listbox.curselection()
        if not sel or not self.os_sequences:
            messagebox.showwarning('No selection', 'Select a sequence first.')
            return
        idx = sel[0]
        if idx >= len(self.os_sequences):
            return
        sid, title = self.os_sequences[idx]
        if sid in self._os_favorites.fav_ids():
            self.os_status.config(text='Already in favorites.')
            return
        if not self._os_favorites.add(sid, title):
            self.os_status.config(text='Already in favorites.')
            return
        fav_ids = self._os_favorites.fav_ids()
        rest = [x for x in self.os_sequences if x[0] not in fav_ids]
        self.os_sequences = list(self._os_favorites.list_all()) + rest
        self._refresh_os_listbox()
        if self.os_sequences:
            try:
                new_idx = next(i for i, (s, _) in enumerate(self.os_sequences) if s == sid)
                self.os_listbox.selection_clear(0, tk.END)
                self.os_listbox.selection_set(new_idx)
                self.os_listbox.see(new_idx)
            except StopIteration:
                pass
        self.os_status.config(text=f'Added to favorites: {title[:40]}…' if len(title) > 40 else f'Added to favorites: {title}')

    def _os_remove_from_favorites(self):
        sel = self.os_listbox.curselection()
        if not sel or not self.os_sequences:
            messagebox.showwarning('No selection', 'Select a sequence first.')
            return
        idx = sel[0]
        if idx >= len(self.os_sequences):
            return
        sid, title = self.os_sequences[idx]
        if sid not in self._os_favorites.fav_ids():
            self.os_status.config(text='Not in favorites.')
            return
        self._os_favorites.remove(sid)
        fav_ids = self._os_favorites.fav_ids()
        rest = [x for x in self.os_sequences if x[0] not in fav_ids]
        self.os_sequences = list(self._os_favorites.list_all()) + rest
        self._refresh_os_listbox()
        if self.os_sequences:
            self.os_listbox.selection_set(0)
            self.os_listbox.see(0)
        self.os_status.config(text='Removed from favorites.')

    def _load_and_play_sequence(self):
        """Download selected sequence, optionally show instrument picker, then start playback."""
        if not playback.KEYBOARD_AVAILABLE:
            messagebox.showerror(
                'Missing dependency',
                'pynput srcrary not available. Install with: pip install pynput'
            )
            return
        sel = self.os_listbox.curselection()
        if not sel or not self.os_sequences:
            messagebox.showwarning('No selection', 'Load list and select a sequence first.')
            return
        idx = sel[0]
        if idx >= len(self.os_sequences):
            return
        sid, title = self.os_sequences[idx]
        self.os_status.config(text=f'Downloading sequence {sid}…')
        tempo = self.tempo.get()
        transpose = self.transpose.get()

        def do_load_and_play():
            try:
                binary = fetch_sequence_binary(sid, timeout=20)
                instruments = get_sequence_instruments(binary)
                self.root.after(
                    0,
                    lambda: self._on_os_binary_loaded_for_play(binary, sid, tempo, transpose, instruments),
                )
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror('Load failed', str(e)))
                self.root.after(0, lambda: self.os_status.config(text='Load failed.'))

        threading.Thread(target=do_load_and_play, daemon=True).start()

    def _on_os_binary_loaded_for_play(
        self,
        binary: bytes,
        sid: str,
        tempo: float,
        transpose: int,
        instruments: list[tuple[int, str]],
    ):
        """On main thread: if 2+ instruments show dialog (sync: assignment dialog; else simple); else convert and start."""
        if len(instruments) < 2:
            try:
                path = sequence_binary_to_midi(binary, bpm=110)
            except Exception as e:
                messagebox.showerror('Load failed', str(e))
                self.os_status.config(text='Load failed.')
                return
            self._on_os_downloaded_for_play(path, sid, tempo, transpose)
            return
        if self._room.is_host():
            self._show_os_sync_assign_dialog(binary, sid, tempo, transpose, instruments)
        else:
            self._show_os_instruments_dialog(binary, sid, tempo, transpose, instruments)

    def _show_os_instruments_dialog(
        self,
        binary: bytes,
        sid: str,
        tempo: float,
        transpose: int,
        instruments: list[tuple[int, str]],
    ):
        """Show modal dialog with instrument checkboxes. Remembers last selection per sequence (in-memory)."""
        top = tk.Toplevel(self.root)
        top.title('Select instruments to play')
        top.configure(bg=BG)
        top.transient(self.root)
        top.grab_set()
        frame = tk.Frame(top, bg=BG, padx=PAD, pady=PAD)
        frame.pack(fill='both', expand=True)
        tk.Label(
            frame, text='Select which instruments to include:', font=LABEL_FONT, fg=FG, bg=BG
        ).pack(anchor='w')
        last_selected = self._os_last_instruments.get(sid)
        vars_by_id: dict[int, tk.BooleanVar] = {}
        cb_frame = tk.Frame(frame, bg=BG)
        cb_frame.pack(fill='x', pady=(SMALL_PAD, PAD))
        for inst_id, name in instruments:
            # Use last selection for this sequence if we have it; otherwise default checked
            checked = (inst_id in last_selected) if last_selected is not None else True
            var = tk.BooleanVar(value=checked)
            vars_by_id[inst_id] = var
            tk.Checkbutton(
                cb_frame,
                text=name,
                variable=var,
                font=SMALL_FONT,
                fg=FG,
                bg=BG,
                activeforeground=FG,
                activebackground=BG,
                selectcolor=ENTRY_BG,
                cursor='hand2',
                anchor='w',
            ).pack(anchor='w')
        btn_style = dict(
            font=LABEL_FONT,
            bg=SUBTLE,
            fg=FG,
            activebackground=ACCENT,
            activeforeground=FG,
            relief='flat',
            padx=BTN_PAD[0],
            pady=BTN_PAD[1],
            cursor='hand2',
        )

        def all_selected():
            return all(v.get() for v in vars_by_id.values())

        def update_toggle_label(*_):
            toggle_btn.config(text='Deselect all' if all_selected() else 'Select all')

        def toggle_select_all():
            select = not all_selected()
            for v in vars_by_id.values():
                v.set(select)
            update_toggle_label()

        toggle_btn = tk.Button(
            frame, text='Deselect all' if all_selected() else 'Select all',
            command=toggle_select_all, **btn_style
        )
        toggle_btn.pack(anchor='w', pady=(0, SMALL_PAD))
        for v in vars_by_id.values():
            v.trace_add('write', update_toggle_label)

        def on_play():
            selected = {i for i, v in vars_by_id.items() if v.get()}
            if not selected:
                messagebox.showwarning('No instrument selected', 'Select at least one instrument.')
                return
            self._os_last_instruments[sid] = selected
            top.destroy()
            try:
                path = sequence_binary_to_midi(binary, bpm=110, instrument_ids=selected)
            except Exception as e:
                messagebox.showerror('Load failed', str(e))
                self.os_status.config(text='Load failed.')
                return
            self._on_os_downloaded_for_play(path, sid, tempo, transpose)

        def on_cancel():
            top.destroy()
            self.os_status.config(text='Ready — focus the game window before playing')

        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill='x', pady=(PAD, 0))
        tk.Button(btn_frame, text='Play', command=on_play, **btn_style).pack(side='left', padx=(0, BTN_GAP))
        tk.Button(btn_frame, text='Cancel', command=on_cancel, **btn_style).pack(side='left')

    def _show_os_sync_assign_dialog(
        self,
        binary: bytes,
        sid: str,
        tempo: float,
        transpose: int,
        instruments: list[tuple[int, str]],
    ):
        """Show dialog for host to assign instruments to each participant (Host + Participant 1, 2, ...). Everyone must have at least one."""
        n_clients = self._room.client_count()
        participant_names = ["Host"] + [f"Participant {i + 1}" for i in range(n_clients)]
        top = tk.Toplevel(self.root)
        top.title('Assign instruments (Play together)')
        top.configure(bg=BG)
        top.transient(self.root)
        top.grab_set()
        frame = tk.Frame(top, bg=BG, padx=PAD, pady=PAD)
        frame.pack(fill='both', expand=True)
        tk.Label(
            frame,
            text='Assign at least one instrument to each participant. Same instrument can be assigned to multiple people.',
            font=SMALL_FONT, fg=FG, bg=BG, wraplength=400, justify='left',
        ).pack(anchor='w')
        # participant_index -> { inst_id -> BooleanVar }
        vars_by_participant: list[dict[int, tk.BooleanVar]] = []
        last_sync = self._os_last_sync_assignments.get(sid)  # list of sets per participant, or None
        for p_idx, p_name in enumerate(participant_names):
            row_frame = tk.LabelFrame(frame, text=f'  {p_name}  ', font=SMALL_FONT, fg=SUBTLE, bg=CARD, labelanchor='n')
            row_frame.pack(fill='x', pady=(SMALL_PAD, 0))
            inner = tk.Frame(row_frame, bg=CARD)
            inner.pack(fill='x', padx=SMALL_PAD, pady=(2, SMALL_PAD))
            vars_by_id: dict[int, tk.BooleanVar] = {}
            part_set = last_sync[p_idx] if last_sync and p_idx < len(last_sync) else None
            for inst_id, name in instruments:
                if part_set is not None:
                    checked = inst_id in part_set
                else:
                    checked = True
                var = tk.BooleanVar(value=checked)
                vars_by_id[inst_id] = var
                tk.Checkbutton(
                    inner,
                    text=name,
                    variable=var,
                    font=SMALL_FONT,
                    fg=FG,
                    bg=CARD,
                    activeforeground=FG,
                    activebackground=CARD,
                    selectcolor=ENTRY_BG,
                    cursor='hand2',
                    anchor='w',
                ).pack(side='left', padx=(0, PAD))
            vars_by_participant.append(vars_by_id)
        btn_style = dict(
            font=LABEL_FONT,
            bg=SUBTLE,
            fg=FG,
            activebackground=ACCENT,
            activeforeground=FG,
            relief='flat',
            padx=BTN_PAD[0],
            pady=BTN_PAD[1],
            cursor='hand2',
        )

        def all_sync_selected():
            return all(v.get() for vars_by_id in vars_by_participant for v in vars_by_id.values())

        def update_sync_toggle_label(*_):
            toggle_btn.config(text='Deselect all' if all_sync_selected() else 'Select all')

        def toggle_sync_select_all():
            select = not all_sync_selected()
            for vars_by_id in vars_by_participant:
                for v in vars_by_id.values():
                    v.set(select)
            update_sync_toggle_label()

        toggle_btn = tk.Button(
            frame, text='Deselect all' if all_sync_selected() else 'Select all',
            command=toggle_sync_select_all, **btn_style
        )
        toggle_btn.pack(anchor='w', pady=(SMALL_PAD, 0))
        for vars_by_id in vars_by_participant:
            for v in vars_by_id.values():
                v.trace_add('write', update_sync_toggle_label)

        def on_play():
            selections: list[set[int]] = []
            for vars_by_id in vars_by_participant:
                sel = {i for i, v in vars_by_id.items() if v.get()}
                selections.append(sel)
            for i, sel in enumerate(selections):
                if not sel:
                    messagebox.showwarning(
                        'Select instruments',
                        f'Assign at least one instrument to {participant_names[i]}.',
                    )
                    return
            host_selection = selections[0]
            client_assignments = [list(selections[i]) for i in range(1, len(selections))]
            self._os_last_instruments[sid] = host_selection
            self._os_last_sync_assignments[sid] = [selections[i] for i in range(len(selections))]
            top.destroy()
            try:
                path = sequence_binary_to_midi(binary, bpm=110, instrument_ids=host_selection)
            except Exception as e:
                messagebox.showerror('Load failed', str(e))
                self.os_status.config(text='Load failed.')
                return
            self._on_os_downloaded_for_play(path, sid, tempo, transpose, instrument_assignments=client_assignments)

        def on_cancel():
            top.destroy()
            self.os_status.config(text='Ready — focus the game window before playing')

        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill='x', pady=(PAD, 0))
        tk.Button(btn_frame, text='Play', command=on_play, **btn_style).pack(side='left', padx=(0, BTN_GAP))
        tk.Button(btn_frame, text='Cancel', command=on_cancel, **btn_style).pack(side='left')

    def _on_os_downloaded_for_play(self, path: str, sid: str, tempo: float, transpose: int, instrument_assignments: list[list[int]] | None = None):
        """Called on main thread when OS MIDI is downloaded. If host, broadcast and sync start; else start now."""
        if self._room.is_host():
            title = next((t for s, t in self.os_sequences if s == sid), None)
            host_label = f"OS: {title}" if title else f"OS: {sid}"
            log.info("Host sending play_os sid=%s (synced)", sid)
            host_send_time = self._room.send_play_os(
                START_DELAY_SEC, sid, tempo, transpose,
                host_playing_label=host_label,
                instrument_assignments=instrument_assignments,
            )
            self._room.host_report_playing(host_label)
            start_at = (host_send_time if host_send_time is not None else time.time()) + START_DELAY_SEC
            # Apply local timing adjustment so host can nudge their own start earlier/later if needed
            start_at += self._sync_local_offset_sec()
            def wait_then_play():
                delay = start_at - time.time()
                if delay > 0:
                    time.sleep(delay)
                self.root.after(0, lambda: self._sync_start_os_playback(path, tempo, transpose))
            threading.Thread(target=wait_then_play, daemon=True).start()
            self.os_status.config(text=f'Starting in {int(START_DELAY_SEC)}s… (synced)')
        else:
            self._os_start_playback(path, tempo, transpose)

    def _os_start_playback(self, path: str, tempo_multiplier: float, transpose: int, keep_source: bool = False):
        """Start playback for an OS-downloaded MIDI path (called on main thread). If keep_source True, do not set _current_source (playlist)."""
        self._os_last_midi_path = path
        self.os_status.config(text='Playing… (focus game window)')
        self.root.focus_set()
        focus_process_window('wwm.exe')
        if not keep_source:
            self._current_source = 'os'
        self._stopped_by_user = False
        self.playing = True
        self.play_btn.config(state='disabled')
        self.os_play_btn.config(state='disabled')
        if hasattr(self, 'pl_play_btn'):
            self.pl_play_btn.config(state='disabled')
        # Stop buttons enabled in _set_progress when playback actually starts
        self.status.config(text='Playing… (focus game window)')
        self._os_playing_path = path
        threading.Thread(
            target=self._play_thread,
            args=(path, tempo_multiplier, transpose),
            daemon=True
        ).start()
        self._start_focus_check()

    def _download_os_midi(self):
        """Download selected sequence as MIDI and save to a file chosen by the user."""
        sel = self.os_listbox.curselection()
        if not sel or not self.os_sequences:
            messagebox.showwarning(
                'No selection',
                'Load list and select a sequence first.'
            )
            return
        idx = sel[0]
        if idx >= len(self.os_sequences):
            return
        sid, title = self.os_sequences[idx]
        self.os_status.config(text='Downloading…')

        def do_download():
            try:
                path = download_sequence_midi(sid, bpm=110, timeout=20)
                self.root.after(0, lambda: self._on_os_midi_downloaded(path, sid, title))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror('Download failed', str(e)))
                self.root.after(0, lambda: self.os_status.config(text='Download failed.'))

        threading.Thread(target=do_download, daemon=True).start()

    def _on_os_midi_downloaded(self, temp_path: str, sid: str, title: str):
        """Called on main thread with the temp MIDI path; show Save As and copy."""
        safe_name = "".join(c for c in title[:40] if c.isalnum() or c in " -_").strip() or f"sequence_{sid}"
        if len(safe_name) > 35:
            safe_name = safe_name[:35]
        default_name = f"{safe_name}.mid"
        out = filedialog.asksaveasfilename(
            defaultextension='.mid',
            filetypes=[('MIDI', '*.mid')],
            initialfile=default_name,
        )
        if not out:
            self.os_status.config(text='Download ready (save cancelled).')
            return
        try:
            shutil.copy2(temp_path, out)
            self.os_status.config(text=f'Saved {os.path.basename(out)}')
        except OSError as e:
            messagebox.showerror('Save failed', str(e))
            self.os_status.config(text='Save failed.')

    def open_folder(self):
        folder = filedialog.askdirectory(title='Select folder with MIDI files')
        if not folder:
            return
        self.folder_path = folder
        self.folder_label.config(text=folder[:60] + '...' if len(folder) > 60 else folder)
        self.file_listbox.delete(0, tk.END)
        try:
            names = sorted(
                n for n in os.listdir(folder)
                if n.lower().endswith('.mid') or n.lower().endswith('.midi')
            )
            for n in names:
                self.file_listbox.insert(tk.END, n)
            if names:
                self.file_listbox.selection_set(0)
                self.file_listbox.see(0)
                self._last_file_path = os.path.join(folder, names[0])
                self._last_tab_visited = 'file'
            else:
                self._last_file_path = None
        except OSError as e:
            messagebox.showerror('Error', str(e))
        self._sync_update_your_selection_label()

    def get_selected_file(self):
        if not self.folder_path:
            return None
        sel = self.file_listbox.curselection()
        if not sel:
            return None
        name = self.file_listbox.get(sel[0])
        return os.path.join(self.folder_path, name)

    def _playlist_display_line(self, item: tuple[str, ...]) -> str:
        if item[0] == 'file':
            return os.path.basename(item[1])
        # 'os', sid, title
        title = item[2][:50] + '…' if len(item[2]) > 50 else item[2]
        return f"{title}  (ID: {item[1]})"

    def _refresh_playlist_listbox(self):
        self.playlist_listbox.delete(0, tk.END)
        for item in self._playlist.items():
            self.playlist_listbox.insert(tk.END, self._playlist_display_line(item))
        n = len(self._playlist)
        if not self.playing:
            self.pl_status.config(
                text=f'{n} song{"s" if n != 1 else ""} in playlist.' if n else 'Playlist is empty.'
            )

    def _pl_select_playing(self):
        """Select and scroll to the currently playing item in the playlist listbox."""
        if self._current_source != 'playlist' or self._playlist.current_index() >= len(self._playlist):
            return
        self.playlist_listbox.selection_clear(0, tk.END)
        self.playlist_listbox.selection_set(self._playlist.current_index())
        self.playlist_listbox.see(self._playlist.current_index())
        self.playlist_listbox.activate(self._playlist.current_index())

    def _add_file_to_playlist(self):
        if not self.folder_path:
            messagebox.showwarning('No folder', 'Open a folder first.')
            return
        sel = list(self.file_listbox.curselection())
        if not sel:
            messagebox.showwarning('No selection', 'Select one or more MIDI files to add.')
            return
        for idx in sel:
            name = self.file_listbox.get(idx)
            path = os.path.join(self.folder_path, name)
            self._playlist.add_file(path)
        self._refresh_playlist_listbox()

    def _add_os_to_playlist(self):
        sel = list(self.os_listbox.curselection())
        if not sel or not self.os_sequences:
            messagebox.showwarning('No selection', 'Load list and select one or more sequences to add.')
            return
        for idx in sel:
            if idx < len(self.os_sequences):
                sid, title = self.os_sequences[idx]
                self._playlist.add_os(sid, title)
        self._refresh_playlist_listbox()

    def _remove_from_playlist(self):
        sel = list(self.playlist_listbox.curselection())
        if not sel:
            return
        self._playlist.remove_indices(sorted(sel, reverse=True))
        self._refresh_playlist_listbox()

    def _clear_playlist(self):
        self._playlist.clear()
        self._refresh_playlist_listbox()

    def _play_playlist(self):
        if not playback.KEYBOARD_AVAILABLE:
            messagebox.showerror(
                'Missing dependency',
                'pynput srcrary not available. Install with: pip install pynput'
            )
            return
        if not self._playlist:
            messagebox.showwarning('Empty playlist', 'Add songs from the File or Online Sequencer tab first.')
            return
        self.root.focus_set()
        focus_process_window('wwm.exe')
        self._current_source = 'playlist'
        self._playlist.reset_to_start()
        self._stopped_by_user = False
        self.playing = True
        self.play_btn.config(state='disabled')
        self.os_play_btn.config(state='disabled')
        self.pl_play_btn.config(state='disabled')
        # Stop buttons enabled in _set_progress when playback actually starts
        n = len(self._playlist)
        self.status.config(text=f'Playing 1/{n}… (focus game window)')
        self.os_status.config(text=f'Playing 1/{n}… (focus game window)')
        self.pl_status.config(text=f'Playing 1/{n}… (focus game window)')
        self._pl_select_playing()
        self._start_next_playlist_item()

    def _start_file_playback(self, path: str, track_indices: set[int] | None = None, keep_source: bool = False):
        """Start playback of a file MIDI. If keep_source is True, do not set _current_source (used by playlist)."""
        if not keep_source:
            self._current_source = 'file'
        self._stopped_by_user = False
        self.playing = True
        self.play_btn.config(state='disabled')
        self.os_play_btn.config(state='disabled')
        if hasattr(self, 'pl_play_btn'):
            self.pl_play_btn.config(state='disabled')
        # Stop buttons enabled in _set_progress when playback actually starts
        self.status.config(text='Playing... (focus game window)')
        threading.Thread(
            target=self._play_thread,
            args=(path, self.tempo.get(), self.transpose.get()),
            kwargs={'track_indices': track_indices},
            daemon=True
        ).start()
        self._start_focus_check()

    def _start_next_playlist_item(self):
        """Start playback of the current playlist item (main thread). Advances to next when finished via _on_playback_finished."""
        if self._playlist.current_index() >= len(self._playlist):
            self.root.after(0, self._progress_done)
            return
        item = self._playlist.current_item()
        if not item:
            self.root.after(0, self._progress_done)
            return
        n = len(self._playlist)
        self.status.config(text=f'Playing {self._playlist.current_index() + 1}/{n}… (focus game window)')
        self.os_status.config(text=f'Playing {self._playlist.current_index() + 1}/{n}… (focus game window)')
        self.pl_status.config(text=f'Playing {self._playlist.current_index() + 1}/{n}… (focus game window)')
        self._pl_select_playing()
        if item[0] == 'file':
            self._start_file_playback(item[1], keep_source=True)
        else:
            sid, title = item[1], item[2]
            tempo = self.tempo.get()
            transpose = self.transpose.get()

            def do_download():
                try:
                    path = download_sequence_midi(sid, bpm=110, timeout=20)
                    self.root.after(0, lambda: self._os_start_playback(path, tempo, transpose, keep_source=True))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror('Load failed', str(e)))
                    self.root.after(0, lambda: self.pl_status.config(text='Load failed.'))
                    self.playing = False
                    self.root.after(0, self._progress_done)

            threading.Thread(target=do_download, daemon=True).start()

    def _os_display_line(self, sid: str, title: str) -> str:
        prefix = '★ ' if sid in self._os_favorites.fav_ids() else '  '
        short = title[:55] + '…' if len(title) > 55 else title
        return f"{prefix}{short}  (ID: {sid})"

    def _refresh_os_listbox(self):
        """Redraw OS listbox from current os_sequences (with ★ for favorites)."""
        self.os_listbox.delete(0, tk.END)
        for sid, title in self.os_sequences:
            self.os_listbox.insert(tk.END, self._os_display_line(sid, title))

    def _apply_file_scale_sizes(self):
        """Apply tempo/transpose row width to scales (called from after_idle so layout is done)."""
        try:
            tr = self._tempo_scale.master
            if tr.winfo_width() > 1:
                self._tempo_scale.config(length=max(60, tr.winfo_width()))
            tr2 = self._transpose_scale.master
            if tr2.winfo_width() > 1:
                self._transpose_scale.config(length=max(60, tr2.winfo_width()))
        except tk.TclError:
            pass

    def _get_file_song_key(self) -> str | None:
        path = self.get_selected_file()
        return os.path.normpath(path) if path else None

    def _get_os_song_key(self) -> str | None:
        sel = self.os_listbox.curselection()
        if not sel or not self.os_sequences:
            return None
        idx = sel[0]
        if idx >= len(self.os_sequences):
            return None
        sid, _ = self.os_sequences[idx]
        return f'os:{sid}'

    def _apply_song_settings_for_key(self, key: str | None):
        """Set tempo and transpose from saved settings for this song, or defaults when none saved."""
        if not key:
            return
        s = self._song_settings.get(key)
        if s is None:
            self.tempo.set(1.0)
            self.transpose.set(0)
            return
        if isinstance(s.get('tempo'), (int, float)):
            self.tempo.set(max(0.25, min(1.75, float(s['tempo']))))
        if isinstance(s.get('transpose'), (int, float)):
            self.transpose.set(max(-12, min(12, int(s['transpose']))))

    def _save_tempo_transpose_for_file(self):
        key = self._get_file_song_key()
        if not key:
            messagebox.showwarning('No selection', 'Select a MIDI file first.')
            return
        self._song_settings.set(key, self.tempo.get(), self.transpose.get())
        self.status.config(text='Tempo/transpose saved for this song.')

    def _save_tempo_transpose_for_os(self):
        key = self._get_os_song_key()
        if not key:
            messagebox.showwarning('No selection', 'Select a sequence first.')
            return
        self._song_settings.set(key, self.tempo.get(), self.transpose.get())
        self.os_status.config(text='Tempo/transpose saved for this song.')

    def _show_file_tracks_dialog(self, path: str, tracks: list[tuple[int, str]], on_confirm: Callable[[set[int]], None]):
        """Show modal to select tracks (only when 2+). on_confirm(selected_set) is called when user clicks Play."""
        norm_path = os.path.normpath(path)
        last_selected = self._file_last_tracks.get(norm_path)
        top = tk.Toplevel(self.root)
        top.title('Select tracks to play')
        top.configure(bg=BG)
        top.transient(self.root)
        top.grab_set()
        frame = tk.Frame(top, bg=BG, padx=PAD, pady=PAD)
        frame.pack(fill='both', expand=True)
        tk.Label(
            frame, text='Select which tracks to include:', font=LABEL_FONT, fg=FG, bg=BG
        ).pack(anchor='w')
        vars_by_idx: dict[int, tk.BooleanVar] = {}
        cb_frame = tk.Frame(frame, bg=BG)
        cb_frame.pack(fill='x', pady=(SMALL_PAD, PAD))
        for idx, name in tracks:
            checked = (idx in last_selected) if last_selected is not None else True
            var = tk.BooleanVar(value=checked)
            vars_by_idx[idx] = var
            tk.Checkbutton(
                cb_frame,
                text=name,
                variable=var,
                font=SMALL_FONT,
                fg=FG,
                bg=BG,
                activeforeground=FG,
                activebackground=BG,
                selectcolor=ENTRY_BG,
                cursor='hand2',
                anchor='w',
            ).pack(anchor='w')
        btn_style = dict(
            font=LABEL_FONT,
            bg=SUBTLE,
            fg=FG,
            activebackground=ACCENT,
            activeforeground=FG,
            relief='flat',
            padx=BTN_PAD[0],
            pady=BTN_PAD[1],
            cursor='hand2',
        )

        def all_tracks_selected():
            return all(v.get() for v in vars_by_idx.values())

        def update_tracks_toggle_label(*_):
            toggle_btn.config(text='Deselect all' if all_tracks_selected() else 'Select all')

        def toggle_tracks_select_all():
            select = not all_tracks_selected()
            for v in vars_by_idx.values():
                v.set(select)
            update_tracks_toggle_label()

        toggle_btn = tk.Button(
            frame, text='Deselect all' if all_tracks_selected() else 'Select all',
            command=toggle_tracks_select_all, **btn_style
        )
        toggle_btn.pack(anchor='w', pady=(0, SMALL_PAD))
        for v in vars_by_idx.values():
            v.trace_add('write', update_tracks_toggle_label)

        def on_play():
            selected = {i for i, v in vars_by_idx.items() if v.get()}
            if not selected:
                messagebox.showwarning('No track selected', 'Select at least one track to play.')
                return
            self._file_last_tracks[norm_path] = selected
            top.destroy()
            on_confirm(selected)

        def on_cancel():
            top.destroy()

        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill='x', pady=(PAD, 0))
        tk.Button(btn_frame, text='Play', command=on_play, **btn_style).pack(side='left', padx=(0, BTN_GAP))
        tk.Button(btn_frame, text='Cancel', command=on_cancel, **btn_style).pack(side='left')

    def _on_file_selection_changed(self):
        key = self._get_file_song_key()
        self._apply_song_settings_for_key(key)
        self.save_file_var.set(self._song_settings.has(key) if key else False)
        path = self.get_selected_file()
        if path is not None:
            self._last_file_path = path
            self._last_tab_visited = 'file'
        self._sync_update_your_selection_label()
        self._sync_report_selection()

    def _on_os_selection_changed(self):
        key = self._get_os_song_key()
        self._apply_song_settings_for_key(key)
        self.save_os_var.set(self._song_settings.has(key) if key else False)
        sid, title = self._get_selected_os()
        if sid is not None:
            self._last_os_sid = sid
            self._last_os_title = title
            self._last_tab_visited = 'os'
        self._sync_update_your_selection_label()
        self._sync_report_selection()

    def _do_file_play(self, path: str, track_indices: set[int] | None):
        """Start file playback (or sync broadcast). Called after track selection when needed."""
        self.root.focus_set()
        focus_process_window('wwm.exe')
        if self._room.is_host():
            try:
                with open(path, 'rb') as f:
                    midi_bytes = f.read()
            except OSError as e:
                messagebox.showerror('Error', str(e))
                return
            tempo = self.tempo.get()
            transpose = self.transpose.get()
            host_label = os.path.basename(path)
            log.info("Host sending play_file (synced, %s bytes)", len(midi_bytes))
            host_send_time = self._room.send_play_file(START_DELAY_SEC, midi_bytes, tempo, transpose, host_playing_label=host_label)
            self._room.host_report_playing(host_label)
            start_at = (host_send_time if host_send_time is not None else time.time()) + START_DELAY_SEC
            start_at += self._sync_local_offset_sec()
            def wait_then_play():
                delay = start_at - time.time()
                if delay > 0:
                    time.sleep(delay)
                self.root.after(0, lambda: self._sync_start_file_playback(path, tempo, transpose, track_indices))
            threading.Thread(target=wait_then_play, daemon=True).start()
            self.status.config(text=f'Starting in {int(START_DELAY_SEC)}s… (synced)')
            return
        self._start_file_playback(path, track_indices)

    def play(self):
        if not playback.KEYBOARD_AVAILABLE:
            messagebox.showerror(
                'Missing dependency',
                'pynput srcrary not available. Install with: pip install pynput'
            )
            return
        path = self.get_selected_file()
        if not path:
            messagebox.showwarning('No file', 'Open a folder and select a MIDI file first')
            return
        try:
            tracks = midi.get_midi_track_info(path)
        except Exception as e:
            messagebox.showerror('Error', str(e))
            return
        if len(tracks) < 2:
            self._do_file_play(path, None)
            return
        self._show_file_tracks_dialog(path, tracks, lambda selected: self._do_file_play(path, selected))

    def _set_progress(self, current, total):
        if total <= 0:
            return
        # Enable stop buttons only when playback has actually started (first progress)
        if not self._stop_buttons_enabled:
            self._stop_buttons_enabled = True
            if hasattr(self, 'pl_stop_btn'):
                self.pl_stop_btn.config(state='normal', bg=STOP_RED)
            self.stop_btn.config(state='normal', bg=STOP_RED)
            self.os_stop_btn.config(state='normal', bg=STOP_RED)
        self.progress_bar['maximum'] = total
        self.progress_bar['value'] = current
        self.os_progress_bar['maximum'] = total
        self.os_progress_bar['value'] = current
        if hasattr(self, 'pl_progress_bar'):
            self.pl_progress_bar['maximum'] = total
            self.pl_progress_bar['value'] = current

    def _progress_done(self):
        self.progress_bar['value'] = self.progress_bar['maximum']
        self.os_progress_bar['value'] = self.os_progress_bar['maximum']
        if hasattr(self, 'pl_progress_bar'):
            self.pl_progress_bar['value'] = self.pl_progress_bar['maximum']
        # Only switch to "stopped" state if we're not playing (e.g. we didn't just start a repeat)
        if not self.playing:
            self._cancel_focus_check()
            if getattr(self, '_os_playing_path', None):
                self._os_playing_path = None
            self.play_btn.config(state='normal')
            self.os_play_btn.config(state='normal')
            if hasattr(self, 'pl_play_btn'):
                self.pl_play_btn.config(state='normal')
            if hasattr(self, 'pl_stop_btn'):
                self.pl_stop_btn.config(state='disabled', bg=SUBTLE)
            self.stop_btn.config(state='disabled', bg=SUBTLE)
            self.os_stop_btn.config(state='disabled', bg=SUBTLE)
            self._stop_buttons_enabled = False
            self.os_status.config(text='Finished playing.')
            if self._current_source == 'playlist' and hasattr(self, 'pl_status'):
                self.pl_status.config(text='Finished playing.')
            if self._current_source == 'sync' and hasattr(self, 'sync_status'):
                self.sync_status.config(text='Finished. Waiting for host to play.' if self._room.is_client() else 'You are the host. Select music and press Play — others will follow.')

    def _cancel_focus_check(self):
        """Cancel the periodic check that stops playback when the game loses focus."""
        if self._focus_check_after_id is not None:
            try:
                self.root.after_cancel(self._focus_check_after_id)
            except (tk.TclError, ValueError):
                pass
            self._focus_check_after_id = None

    def _check_game_focus(self):
        """If we're playing and the foreground window is not the game (or our app), stop playback."""
        self._focus_check_after_id = None
        if not self.playing:
            return
        name = get_foreground_process_name()
        if name is None:
            self._focus_check_after_id = self.root.after(500, self._check_game_focus)
            return
        our_exe = os.path.basename(sys.executable).lower()
        if name in ('wwm.exe', our_exe):
            self._focus_check_after_id = self.root.after(500, self._check_game_focus)
            return
        self.stop()

    def _start_focus_check(self):
        """Start periodic check: stop playback when foreground window is not Where Winds Meet or this app."""
        self._cancel_focus_check()
        self._focus_check_after_id = self.root.after(500, self._check_game_focus)

    def stop(self):
        self._stopped_by_user = True
        self.playing = False
        self._cancel_focus_check()
        if self._room.is_host():
            self._room.send_stop()
        self.status.config(text='Stopped')
        if self._current_source == 'playlist' and hasattr(self, 'pl_status'):
            self.pl_status.config(text='Stopped.')
        if self._current_source == 'sync' and hasattr(self, 'sync_status'):
            self.sync_status.config(text='Stopped.')
        self.play_btn.config(state='normal')
        self.os_play_btn.config(state='normal')
        if hasattr(self, 'pl_play_btn'):
            self.pl_play_btn.config(state='normal')
        if hasattr(self, 'pl_stop_btn'):
            self.pl_stop_btn.config(state='disabled', bg=SUBTLE)
        self.stop_btn.config(state='disabled', bg=SUBTLE)
        self.os_stop_btn.config(state='disabled', bg=SUBTLE)
        self._stop_buttons_enabled = False

    def _play_thread(self, path, tempo_multiplier, transpose, track_indices: set[int] | None = None):
        def on_done(finished_naturally: bool):
            self.playing = False
            self.root.after(0, lambda: self._on_playback_finished(finished_naturally))

        try:
            playback.run_playback_from_file(
                path, tempo_multiplier, transpose,
                is_playing=lambda: self.playing,
                progress_callback=lambda c, t: self.root.after(0, lambda c=c, t=t: self._set_progress(c, t)),
                done_callback=on_done,
                track_indices=track_indices,
            )
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror('Playback error', str(e)))
            self.root.after(0, lambda: self.status.config(text='Error'))
            # run_playback_from_file's finally already calls on_done(False) when we raise

    def _on_playback_finished(self, finished_naturally: bool):
        """Run on main thread when playback thread exits. Updates UI and optionally starts repeat or next playlist item."""
        if finished_naturally and not self._stopped_by_user:
            if self._current_source == 'playlist':
                if self._playlist.advance():
                    self.root.after(0, self._start_next_playlist_item)
                    return
                if self.repeat_playlist.get():
                    self._playlist.reset_to_start()
                    self.root.after(0, self._start_next_playlist_item)
                    return
            else:
                self._maybe_repeat_current()
        self._progress_done()

    def _maybe_repeat_current(self):
        """If repeat is enabled, start playback again for the current source."""
        if self._current_source == 'file':
            if self.repeat_file.get():
                self.play()
        elif self._current_source == 'os':
            if self.repeat_os.get():
                path = getattr(self, '_os_last_midi_path', None)
                if path:
                    # Use current tempo/transpose controls
                    self._os_start_playback(path, self.tempo.get(), self.transpose.get())
