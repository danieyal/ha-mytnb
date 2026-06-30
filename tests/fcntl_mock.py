"""Pytest plugin to mock Unix-only modules on Windows and enable sockets."""
import sys
from unittest.mock import MagicMock

# This runs at plugin load time, before homeassistant is imported
if sys.platform == "win32":
    sys.modules["fcntl"] = MagicMock()
    sys.modules["resource"] = MagicMock()


def pytest_runtest_setup():
    """Enable sockets for all tests (pytest-socket blocks them by default)."""
    try:
        import pytest_socket
        pytest_socket.enable_socket()
    except ImportError:
        pass
