"""Request Windows admin (UAC) and re-launch if needed."""

import os
import sys


def request_admin_and_restart() -> None:
    """On Windows, if not running as admin, re-launch with UAC and exit. Otherwise no-op."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        return
    # Re-launch with runas
    try:
        exe = sys.executable
        args = ' '.join(f'"{a}"' for a in sys.argv)
        ctypes.windll.shell32.ShellExecuteW(
            None, 'runas', exe, args, os.getcwd(), 1
        )
    except Exception:
        pass
    sys.exit(0)
