

"""Unit testovi za utils.file_utils."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from utils.file_utils import secure_filename


def test_secure_filename_basic():
    assert secure_filename("knjiga.epub") == "knjiga.epub"


def test_secure_filename_balkan():
    assert secure_filename("Čudna Knjiga.epub") == "Cudna_Knjiga.epub"


def test_secure_filename_empty():
    assert secure_filename("") == "nepoznato.epub"


def test_secure_filename_path_traversal():
    result = secure_filename("../../etc/passwd")
    assert ".." not in result
    assert "/" not in result


def test_secure_filename_only_dots():
    result = secure_filename("...")
    assert result == "knjiga.epub"


def test_secure_filename_special_chars():
    result = secure_filename("my book (2024).epub")
    assert "(" not in result
    assert ")" not in result
    assert result.endswith(".epub")



