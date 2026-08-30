"""Tests for provenance formatting."""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.knowledge.provenance import format_provenance


def test_conversation_provenance():
    s = format_provenance({
        "source_type": "conversation",
        "source_id": "abc123",
        "message_index": 4,
    })
    assert s == "Conversation abc123, Message #4"


def test_file_provenance():
    s = format_provenance({
        "source_type": "file",
        "source_ref": "src/auth/AuthService.ts",
    })
    assert s == "src/auth/AuthService.ts"


def test_symbol_provenance():
    s = format_provenance({
        "source_type": "symbol",
        "file_path": "src/ws/manager.ts",
        "symbol_name": "ConnectionManager",
    })
    assert s == "src/ws/manager.ts (ConnectionManager)"


def test_user_provenance():
    s = format_provenance({"source_type": "user"})
    assert s == "User-provided knowledge"


def test_fallback_unknown():
    s = format_provenance({})
    assert s == "Unknown source"
