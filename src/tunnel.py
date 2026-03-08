"""Public link via ngrok TCP tunnel so friends not on the local network can join the room."""

import logging
import os
from typing import Tuple

log = logging.getLogger("src.tunnel")

# Optional: only used when creating a tunnel
_tunnel = None  # NgrokTunnel | None
_public_url = None  # str | None


def is_available() -> Tuple[bool, str]:
    """Return (True, '') if tunnel API is available; else (False, reason)."""
    token = os.environ.get("NGROK_AUTH_TOKEN", "").strip()
    if not token:
        return False, "Set NGROK_AUTH_TOKEN (get a free token at https://ngrok.com)"
    try:
        from pyngrok import ngrok  # noqa: F401
    except ImportError:
        return False, "Install pyngrok: pip install pyngrok"
    return True, ""


def start_tcp_tunnel(local_port: int) -> Tuple[bool, str, str]:
    """
    Start a TCP tunnel to local_port. Returns (ok, public_addr, error_msg).
    public_addr is 'host:port' for friends to use in Join (e.g. '0.tcp.ngrok.io:12345').
    """
    global _tunnel, _public_url
    ok, reason = is_available()
    if not ok:
        return False, "", reason
    if _tunnel is not None:
        return False, "", "A tunnel is already active. Close it first."
    token = os.environ.get("NGROK_AUTH_TOKEN", "").strip()
    try:
        from pyngrok import ngrok
        # Ensure the ngrok process gets the token (writes to config before starting process)
        ngrok.set_auth_token(token)
        _tunnel = ngrok.connect(str(local_port), proto="tcp")
        _public_url = _tunnel.public_url or ""
        # public_url is like "tcp://0.tcp.ngrok.io:12345" -> we want "0.tcp.ngrok.io:12345"
        if _public_url.startswith("tcp://"):
            addr = _public_url[6:]
        else:
            addr = _public_url
        log.info("Tunnel started: %s -> localhost:%s", addr, local_port)
        return True, addr, ""
    except Exception as e:
        err = str(e).strip() or "Unknown error"
        err_lower = err.lower()
        # Don't log or surface the raw error if it may contain the token
        if "invalid" in err_lower and ("authtoken" in err_lower or "token" in err_lower) or "err_ngrok_107" in err_lower:
            log.warning("Tunnel start failed: ngrok rejected the auth token (invalid or reset)")
            return False, "", (
                "Your ngrok token is invalid or was reset. "
                "Get a new token at https://dashboard.ngrok.com/get-started/your-authtoken"
            )
        if "authtoken" in err_lower or "auth" in err_lower or "token" in err_lower:
            log.warning("Tunnel start failed: auth error (not logging details)")
            return False, "", (
                "Ngrok authentication failed. "
                "Check your token at https://dashboard.ngrok.com/get-started/your-authtoken"
            )
        log.exception("Tunnel start failed")
        return False, "", err


def stop_tunnel() -> bool:
    """Close the current tunnel. Returns True if a tunnel was closed."""
    global _tunnel, _public_url
    if _tunnel is None or _public_url is None:
        return False
    try:
        from pyngrok import ngrok
        ngrok.disconnect(_public_url)
        log.info("Tunnel closed: %s", _public_url)
    except Exception as e:
        log.warning("Tunnel disconnect: %s", e)
    finally:
        _tunnel = None
        _public_url = None
    return True


def get_public_addr() -> str | None:
    """Return current public host:port or None if no tunnel."""
    if _public_url is None:
        return None
    if _public_url.startswith("tcp://"):
        return _public_url[6:]
    return _public_url


def is_tunnel_active() -> bool:
    return _tunnel is not None
