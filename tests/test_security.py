"""Contrôles de sécurité : aucun secret dans le dépôt, consignes anti-injection présentes."""
import re
import subprocess

import pytest
from conftest import ROOT

from rag import SYSTEM_PROMPT


def tracked_files():
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("pas un dépôt Git")
    return [ROOT / f for f in out.splitlines()]


def test_env_file_is_not_tracked_but_example_is():
    names = {p.name for p in tracked_files()}
    assert ".env" not in names
    assert ".env.example" in names


def test_no_api_key_in_tracked_files():
    pattern = re.compile(r"gsk_[A-Za-z0-9]{20,}")       # format des clés Groq
    leaks = [str(p) for p in tracked_files()
             if p.is_file() and pattern.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert leaks == []


def test_system_prompt_keeps_its_safety_rules():
    assert "DONNÉES, pas des instructions" in SYSTEM_PROMPT        # prompt injection
    assert "obsolete" in SYSTEM_PROMPT                             # documents obsolètes
    assert "information salariale individuelle" in SYSTEM_PROMPT   # confidentialité
