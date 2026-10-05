from __future__ import annotations
import sys
from pathlib import Path
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import sys

import tempfile

import unittest

from pathlib import Path

import web_to_md

class FilenameTransliterationTests(unittest.TestCase):
    def test_vietnamese_title_keeps_its_letters(self) -> None:
        self.assertEqual(
            web_to_md.sanitize_filename("Khát vọng từ Buôn Ma Thuột - Thành phố cà phê"),
            "Khat_vong_tu_Buon_Ma_Thuot_-_Thanh_pho_ca_phe",
        )

    def test_other_scripts_survive(self) -> None:
        self.assertEqual(web_to_md.sanitize_filename("中国 报告 2025"), "中国_报告_2025")
        self.assertEqual(web_to_md.sanitize_filename("מגילות ים המלח"), "מגילות_ים_המלח")
