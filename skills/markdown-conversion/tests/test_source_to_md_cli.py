from __future__ import annotations
import sys
from pathlib import Path
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import argparse

import codecs

import io

import json

import subprocess

import sys

import tempfile

import unittest

from contextlib import redirect_stdout

from pathlib import Path

from unittest.mock import Mock, patch

from web_to_md import is_plain_text_document

import web_to_md

from excel_to_md import _format_cell_value

def _args(**overrides: object) -> argparse.Namespace:
    values = dict(
        images=None,
        no_images=False,
        filter_images=False,
        render_vector_figures=False,
    )
    values.update(overrides)
    return argparse.Namespace(**values)

class ImageFlagRoutingTests(unittest.TestCase):
    def test_downloaded_webp_is_oriented_before_png_conversion(self) -> None:
        from PIL import Image

        image = Image.new("RGB", (80, 40), "red")
        exif = image.getexif()
        exif[274] = 6
        encoded = io.BytesIO()
        image.save(encoded, format="WEBP", exif=exif)
        response = Mock(content=encoded.getvalue(), headers={"Content-Type": "image/webp"})
        content = web_to_md.BeautifulSoup('<p><img src="photo.webp"/></p>', "html.parser")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(web_to_md, "_http_get", return_value=response), redirect_stdout(io.StringIO()):
                count = web_to_md.download_and_rewrite_images(content, "https://example.com/", tmp, "images")
            self.assertEqual(count, 1)
            with Image.open(next(Path(tmp).glob("*.png"))) as converted:
                self.assertEqual(converted.size, (40, 80))
                self.assertNotIn(274, converted.getexif())

class RawTextUrlTests(unittest.TestCase):
    def test_markdown_url_with_markdown_body_is_plain_text(self) -> None:
        self.assertTrue(is_plain_text_document(
            "https://raw.githubusercontent.com/astral-sh/uv/main/CHANGELOG.md",
            "# Changelog\n\n## 0.12.10\n\nReleased on 2026-09-04.\n",
        ))
    def test_html_bodies_and_html_urls_still_go_through_the_extractor(self) -> None:
        self.assertFalse(is_plain_text_document(
            "https://example.com/notes.md",
            "<!DOCTYPE html><html><body><p>rendered</p></body></html>",
        ))
        self.assertFalse(is_plain_text_document(
            "https://docs.astral.sh/uv/", "# looks like markdown but is a page",
        ))

class ExcelCellValueTests(unittest.TestCase):
    def test_float_values_keep_excel_display_precision(self) -> None:
        # 15 significant digits, the precision Excel itself displays.
        cases = [
            (1234567.89, "1234567.89"),
            (0.1 + 0.2, "0.3"),
            (100.0, "100"),
            (1e-7, "1e-07"),
            (-0.5, "-0.5"),
            (1.2345678901234567, "1.23456789012346"),
            (-0.0, "-0"),
            (1e20, "1e+20"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                result = _format_cell_value(value)
                self.assertEqual(result, expected)
                self.assertAlmostEqual(float(result), value, delta=abs(value) * 1e-14)

class WebTraversalTests(unittest.TestCase):
    def test_inline_whitespace_is_preserved_once(self) -> None:
        cases = [
            ("<strong>Hello</strong> <em>World</em>", "**Hello** *World*"),
            ('See <a href="x">here</a> now', "See [here](x) now"),
            ("<code>a</code> <code>b</code>", "`a` `b`"),
            ("<strong>Hello</strong> \n\t <em>World</em>", "**Hello** *World*"),
            ("<strong>Hello</strong> <!-- comment --> <em>World</em>", "**Hello** *World*"),
            ("<strong>Hello</strong><em>World</em>", "**Hello***World*"),
        ]
        for html, expected in cases:
            with self.subTest(html=html):
                soup = web_to_md.BeautifulSoup(f"<p>{html}</p>", "html.parser")
                self.assertEqual(web_to_md.simple_html_to_markdown_traversal(soup), expected)

    def test_block_whitespace_does_not_leak_into_paragraphs(self) -> None:
        cases = [
            ("<p>one</p> \n <p>two</p>", "one\n\ntwo"),
            ("<div>one</div> \n <div>two</div>", "one\n\ntwo"),
            ("<section>one</section> \n <section>two</section>", "one\n\ntwo"),
            ("<ul> <li>one</li> <li>two</li> </ul>", "- one\n- two"),
            ("<p>  lead</p>", "lead"),
            ("<p>  lead</p><p>trail  </p>", "lead\n\ntrail"),
            ("<p> <strong>Hello</strong> <em>World</em> </p>", "**Hello** *World*"),
        ]
        for html, expected in cases:
            with self.subTest(html=html):
                soup = web_to_md.BeautifulSoup(html, "html.parser")
                self.assertEqual(web_to_md.simple_html_to_markdown_traversal(soup), expected)

    def test_preformatted_text_and_explicit_line_breaks_keep_spacing(self) -> None:
        cases = [
            ("<pre> a\n  b </pre>", "```\n a\n  b \n```"),
            ("<p>one<br>two</p>", "one  \ntwo"),
        ]
        for html, expected in cases:
            with self.subTest(html=html):
                soup = web_to_md.BeautifulSoup(html, "html.parser")
                self.assertEqual(web_to_md.simple_html_to_markdown_traversal(soup), expected)

    def test_links_resolve_relative_targets_and_keep_special_targets(self) -> None:
        cases = [
            ("../target", "[label](https://example.com/target)"),
            ("/abs", "[label](https://example.com/abs)"),
            ("//cdn.x/y", "[label](https://cdn.x/y)"),
            ("#frag", "[label](#frag)"),
            ("mailto:reader@example.com", "[label](mailto:reader@example.com)"),
            ("tel:+123456789", "[label](tel:+123456789)"),
            ("javascript:void(0)", "label"),
            ("JavaScript:void(0)", "label"),
        ]
        for href, expected in cases:
            with self.subTest(href=href):
                soup = web_to_md.BeautifulSoup(f'<p><a href="{href}">label</a></p>', "html.parser")
                self.assertEqual(
                    web_to_md.simple_html_to_markdown_traversal(soup, "https://example.com/a/page"),
                    expected,
                )

    def test_process_url_resolves_against_redirect_and_first_base_href(self) -> None:
        cases = [
            ("", "https://redirect.example/docs/"),
            ('<base href="https://base.example/root/">', "https://base.example/root/"),
            ('<base href="../assets/">', "https://redirect.example/assets/"),
            ('<base target="_blank"><base href="/first/"><base href="/ignored/">',
             "https://redirect.example/first/"),
        ]
        for base, expected_base in cases:
            with self.subTest(base=base), tempfile.TemporaryDirectory() as tmp:
                html = (
                    f"<html><head><title>Links</title>{base}</head><body>"
                    '<p><a href="target">target</a> <img src="pic.png" alt="pic"></p>'
                    "</body></html>"
                )
                response = Mock(
                    content=html.encode("utf-8"),
                    headers={"Content-Type": "text/html; charset=utf-8"},
                    encoding="utf-8",
                    apparent_encoding="utf-8",
                    url="https://redirect.example/docs/page",
                )
                response.raise_for_status.return_value = None
                output = Path(tmp) / "page.md"
                with patch.object(web_to_md, "_http_get", return_value=response), redirect_stdout(io.StringIO()):
                    result = web_to_md.process_url(
                        "https://original.example/start", str(output), download_images=False,
                    )
                self.assertTrue(result[0], result[2])
                markdown = output.read_text(encoding="utf-8")
                self.assertIn(f"[target]({expected_base}target)", markdown)
                self.assertIn(f"![pic]({expected_base}pic.png)", markdown)

class TypstFallbackTests(unittest.TestCase):
    def test_project_file_with_imports_keeps_text_and_maps_headings(self) -> None:
        from doc_to_md import convert_to_markdown

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "chapter.typ"
            source.write_text(
                '#import "mod.typ": *\n'
                "#show: book.page.with(title: [Intro])\n\n"
                "= Headings\n\n"
                "Write *markup* here.\n\n"
                "#code(```typ\n= Not a heading\n```)\n\n"
                "== Next\n",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                markdown = convert_to_markdown(str(source))

            lines = markdown.splitlines()
            self.assertIn("# Headings", lines)
            self.assertIn("## Next", lines)
            self.assertIn("= Not a heading", lines)
            self.assertIn("Write *markup* here.", lines)
            profile = json.loads(source.with_suffix(".conversion_profile.json").read_text(encoding="utf-8"))
            self.assertTrue(any("headings mapped" in warning for warning in profile["warnings"]))
