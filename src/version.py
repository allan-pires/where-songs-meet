"""Application version and update configuration."""

__version__ = "1.2.10"

# GitHub repo for update checks: "owner/repo"
GITHUB_REPO = "allan-pires/where-songs-meet"

GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
