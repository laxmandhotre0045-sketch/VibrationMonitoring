"""The runner's argument splitting and isolation check.

Both of these were wrong when first written, which is why they are tested:
the documented command line did not work, and an isolation check that cannot
fail proves nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_agent import AGENTS, _fingerprint, _other_agents_paths, _split_runner_flags


# ------------------------------------------------------------- flag split --


def test_runner_flag_after_the_agent_name_is_recognised():
    """The documented form. argparse.REMAINDER swallowed this originally, so
    --with-books reached the agent and the runner never saw it."""
    mine, rest = _split_runner_flags(["kb", "--with-books", "ask", "why"])
    assert "--with-books" in mine
    assert rest == ["ask", "why"]


def test_runner_flags_come_before_the_agent_name_when_reassembled():
    """REMAINDER starts at the first token after the positional, so anything of
    ours left behind the agent name would be handed to the agent instead."""
    mine, _ = _split_runner_flags(["kb", "--with-books", "docs"])
    assert mine.index("--with-books") < mine.index("kb")


def test_flag_before_the_agent_name_also_works():
    mine, rest = _split_runner_flags(["--with-books", "kb", "docs"])
    assert "--with-books" in mine and rest == ["docs"]


def test_agent_flags_are_not_stolen_by_the_runner():
    """--separate-driver belongs to report_agent and must pass straight through."""
    mine, rest = _split_runner_flags(["report", "build", "pump", "--separate-driver"])
    assert mine == ["report"]
    assert rest == ["build", "pump", "--separate-driver"]


def test_model_option_takes_its_value_with_it():
    mine, rest = _split_runner_flags(["kb", "--model", "gpt-4o", "ask", "why"])
    assert mine[:2] == ["--model", "gpt-4o"]
    assert rest == ["ask", "why"]


# -------------------------------------------------------------- isolation --


def test_fingerprint_detects_a_write(tmp_path):
    """The check must be able to fail, or it says nothing."""
    before = _fingerprint(tmp_path)
    (tmp_path / "new.txt").write_text("x", encoding="utf-8")
    assert _fingerprint(tmp_path) != before


def test_fingerprint_of_a_missing_directory_is_stable(tmp_path):
    missing = tmp_path / "not-there"
    assert _fingerprint(missing) == _fingerprint(missing) == (0, 0, 0.0)


def test_an_agent_is_never_asked_to_watch_its_own_paths():
    for spec in AGENTS.values():
        watched = _other_agents_paths(spec)
        for rel in spec.writes:
            assert not any(label.startswith(f"{spec.name}:") for label in watched), (
                f"{spec.name} would be flagged for writing to its own {rel}"
            )


@pytest.mark.parametrize("name,spec", list(AGENTS.items()))
def test_every_agent_declares_a_runnable_module(name, spec):
    import importlib
    module = importlib.import_module(f"{spec.module}.__main__")
    assert callable(getattr(module, "main", None)), f"{spec.module} has no main()"
