"""Loguru operation logging setup.

Installs a single rotated file sink once at Django startup.
Log path is anchored at BASE_DIR/logs/app.log (independent of cwd).
"""

from pathlib import Path

from loguru import logger


def setup_logging() -> None:
    """Install the rotated file sink exactly once (safe to call repeatedly)."""
    log_path = Path(__file__).resolve().parent.parent / "logs" / "app.log"
    logger.add(
        str(log_path),
        level="INFO",
        rotation="10 MB",
        retention="4 weeks",
        diagnose=False,
        catch=True,
    )
