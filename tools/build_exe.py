"""Build a single-file Windows executable with PyInstaller. Run from project root."""

import os
import subprocess
import sys


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)

    entry = "main.py"
    if not os.path.isfile(entry):
        print(f"Entry script not found: {entry}")
        sys.exit(1)

    icon_path = os.path.join(root, "where-songs-meet.ico")
    icon_arg = ["--icon", icon_path] if os.path.isfile(icon_path) else []

    manifest_path = os.path.join(root, "manifest.xml")
    manifest_arg = ["--manifest", manifest_path] if os.path.isfile(manifest_path) else []

    try:
        import PyInstaller.__main__
    except ImportError:
        print("PyInstaller required: pip install pyinstaller")
        sys.exit(1)

    hidden = [
        "--hidden-import", "lib.theme",
        "--hidden-import", "lib.icon_images",
        "--hidden-import", "certifi",
    ]

    cmd = (
        [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--windowed",
            "--name", "where-songs-meet",
            "--clean",
            "--noconfirm",
        ]
        + icon_arg
        + manifest_arg
        + hidden
        + [entry]
    )

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=root)
    if result.returncode != 0:
        sys.exit(result.returncode)
    exe_path = os.path.join(root, "dist", "where-songs-meet.exe")
    print("Built:", exe_path)


if __name__ == "__main__":
    main()
