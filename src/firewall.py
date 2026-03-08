"""Add Windows Firewall rules so the app can join/host rooms (private and public networks)."""

import subprocess
import sys


RULE_NAME = "Where Songs Meet"


def add_firewall_rules() -> tuple[bool, str]:
    """
    Add inbound and outbound Windows Firewall rules for the current executable
    for private and public profiles. Requires admin. Returns (success, message).
    """
    if sys.platform != "win32":
        return (False, "Windows only")

    exe = sys.executable
    if not exe or not exe.strip():
        return (False, "Could not get program path.")

    # Remove existing rules with our name to avoid duplicates
    subprocess.run(
        ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={RULE_NAME}"],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )

    # Add inbound and outbound rules (private and public)
    for direction in ("in", "out"):
        cmd = [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={RULE_NAME}",
            f"dir={direction}",
            "action=allow",
            f'program="{exe}"',
            "profile=private,public",
        ]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip() or "Unknown error"
            return (False, err)

    return (True, "Firewall rules added for private and public networks.")
