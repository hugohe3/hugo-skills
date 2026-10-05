import contextlib
import io
import random
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import subtitle_to_md as subtitle
import _image_filter as images
import pdf_to_md_mineru as mineru
from PIL import Image, ImageDraw


class ContentPreservationTests(unittest.TestCase):
    def test_f11_numeric_dialogue(self):
        text = subtitle.process_srt_content("1\n00:00:00,000 --> 00:00:01,000\n数量\n3000000\n2026\n结束\n")
        self.assertIn("3000000 2026", text)

    def test_f12_dialogue_arrow(self):
        for parser, stamp in [(subtitle.process_srt_content, "00:00:00,000"),
                              (subtitle.process_vtt_content, "00:00.000")]:
            with self.subTest(parser=parser.__name__):
                text = parser(f"{stamp} --> {stamp}\n前文\nA --> B 是反应方向\n后文\n")
                self.assertIn("前文 A --> B 是反应方向 后文", text)

    def test_review_subtitle_samples_preserve_all_dialogue(self):
        cases = [
            ("h1crlf.srt", subtitle.process_srt_content,
             "1\r\n0:00:01,000 --> 0:00:02,000\r\nHello one\r\n\r\n"
             "2\r\n0:00:02,500 --> 0:00:03,000\r\n42\r\n\r\n",
             "Hello one 42"),
            ("odd.srt", subtitle.process_srt_content,
             "1\n00:00:01.000 --> 00:00:02.000\nDot millis\n\n"
             "2\n00:00:03,00 --> 00:00:04,00\nTwo-digit millis\n",
             "Dot millis Two-digit millis"),
            ("h1.vtt", subtitle.process_vtt_content,
             "WEBVTT\n\n1\n0:00:01.000 --> 0:00:02.000\nVTT one-digit hour\n\n"
             "00:03.000 --> 00:04.000 align:start\nShort form\n",
             "VTT one-digit hour Short form"),
        ]
        for name, parser, content, expected in cases:
            with self.subTest(sample=name):
                self.assertEqual(expected, parser(content, raw=True))
                text = parser(content)
                self.assertEqual(expected, " ".join(
                    line for line in text.splitlines() if line and not line.startswith("<!--")))

    def test_tolerant_timestamps_preserve_dialogue(self):
        stamps = ["0:0:1", "123:1:02,1", "1:02.12", "00:03.000", "2:3"]
        for parser in (subtitle.process_srt_content, subtitle.process_vtt_content):
            for stamp in stamps:
                for spacing in ("", " ", "\t  "):
                    with self.subTest(parser=parser.__name__, stamp=stamp, spacing=spacing):
                        content = (f"{stamp}{spacing}-->{spacing}{stamp} align:start\r\n"
                                   "前文\r\n3000000\r\nA --> B\r\n"
                                   "00:01 --> 下一步\r\n上一步 --> 00:02\r\n后文\r\n")
                        self.assertEqual(
                            "前文 3000000 A --> B 00:01 --> 下一步 上一步 --> 00:02 后文",
                            parser(content, raw=True))

    def test_f13_webvtt_first_cue(self):
        text = subtitle.process_vtt_content("WEBVTT\nLanguage: zh\n\n00:00:00.000 --> 00:00:01.000\nFIRST_CUE\n\n00:00:01.000 --> 00:00:02.000\nSECOND_CUE\n")
        self.assertIn("FIRST_CUE", text)
        self.assertIn("SECOND_CUE", text)

    def test_f14_literal_html_tags(self):
        text = subtitle.html_to_text("<p>&lt;b&gt;重要&lt;/b&gt; &lt;script&gt;BODY&lt;/script&gt; &amp;lt;b&amp;gt;</p><script>HIDDEN</script>")
        self.assertIn("<b>重要</b>", text)
        self.assertIn("<script>BODY</script>", text)
        self.assertIn("&lt;b&gt;", text)
        self.assertNotIn("HIDDEN", text)

    def test_f15_mixed_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "course"
            chapter = root / "chapter1"
            chapter.mkdir(parents=True)
            cue = "1\n00:00:00,000 --> 00:00:01,000\n"
            (root / "chapter1.srt").write_text(cue + "ROOT_BODY\n")
            (chapter / "lesson.srt").write_text(cue + "CHAPTER_BODY\n")
            out = root / "0-srt"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, subtitle.convert_subtitles(str(root)))
            results = [p.read_text() for p in out.glob("*.md")]
            self.assertEqual(2, len(results))
            self.assertIn("ROOT_BODY", "\n".join(results))
            self.assertIn("CHAPTER_BODY", "\n".join(results))

    def image_bytes(self, noise=False):
        img = (Image.frombytes("RGB", (400, 200), random.Random(42).randbytes(400 * 200 * 3))
               if noise else Image.new("RGB", (400, 200), "white"))
        if not noise:
            ImageDraw.Draw(img).text((30, 60), "E = mc^2", fill="black", font_size=40)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_f16_equation_image(self):
        self.assertTrue(images.should_keep_image_bytes(self.image_bytes()))
        # Compression size alone cannot distinguish formulas from decoration.
        buf = io.BytesIO()
        Image.new("RGB", (400, 200), "white").save(buf, format="PNG")
        self.assertTrue(images.should_keep_image_bytes(buf.getvalue()))
        self.assertTrue(images.should_keep_image_bytes(b"unknown-image-format"))

    def test_f17_repeated_image_positions(self):
        payload = self.image_bytes(noise=True)
        seen = set()
        self.assertTrue(images.should_keep_image_bytes(payload, seen_hashes=seen))
        self.assertTrue(images.should_keep_image_bytes(payload, seen_hashes=seen))
        self.assertEqual(1, len(seen))

    def test_f18_rejected_size_does_not_poison_seen(self):
        payload = self.image_bytes(noise=True)
        seen = set()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertFalse(images.should_keep_image(payload, 400, 200, page_size=(10, 10), render_size=(.01, .01), seen_hashes=seen))
        self.assertIn("[WARN]", err.getvalue())
        self.assertEqual(set(), seen)
        self.assertTrue(images.should_keep_image(payload, 400, 200, page_size=(10, 10), render_size=(3, 2), seen_hashes=seen))

    def test_image_rejection_warning_identifies_dimensions_and_reason(self):
        cases = [
            (50, 200, {}, "dimensions"),
            (100, 100, {}, "area"),
            (400, 200, {"page_size": (10, 10), "render_size": (.01, .01)}, "page-ratio"),
            (2000, 100, {}, "aspect"),
        ]
        for width, height, kwargs, reason in cases:
            with self.subTest(reason=reason), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertFalse(images.should_keep_image(b"image", width, height, **kwargs))
                warning = err.getvalue()
                self.assertIn(f"{width} x {height}, reason={reason}", warning)
                self.assertIn("disable --filter-images", warning)

    def download_zip(self, files, output, **kwargs):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        response = SimpleNamespace(status_code=200, content=buf.getvalue())
        with patch.object(mineru.requests, "get", return_value=response), contextlib.redirect_stdout(io.StringIO()):
            return Path(mineru.MinerUClient("synthetic").download_and_extract("https://example.invalid/result", output, output_filename="result", **kwargs))

    def test_f19_image_cleanup_preserves_code(self):
        literal = "![BODY_CODE](images/drop.png)"
        content = (f"正文\n```markdown\n{literal}\n```\n~~~markdown\n{literal}\n~~~\n"
                   f"    {literal}\n`{literal}`\n\\{literal}\n"
                   f"- ```markdown\n  {literal}\n  ```\n"
                   f"``inline\n{literal}\ncode`` and {literal}\n")
        with tempfile.TemporaryDirectory() as tmp, patch.object(mineru, "should_keep_image_bytes", return_value=False):
            path = self.download_zip({"full.md": content, "images/drop.png": b"image"}, tmp, filter_images=True)
            text = path.read_text()
        self.assertEqual(7, text.count(literal))
        self.assertNotEqual(content, text)
        self.assertEqual(text, mineru.strip_image_refs(content))
        self.assertEqual(content, mineru.strip_image_refs_by_filenames(content, {"other.png"}))

    def test_s03_multiple_markdown_warns_and_preserves(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()) as err:
            path = self.download_zip({"a.md": "FIRST_BODY", "part/b.md": "SECOND_BODY"}, tmp)
            self.assertIn("FIRST_BODY", path.read_text())
            preserved = Path(tmp) / "mineru/result/part/b.md"
            self.assertEqual("SECOND_BODY", preserved.read_text())
            self.assertIn("part/b.md", err.getvalue())
            self.assertIn(str(preserved), err.getvalue())


if __name__ == "__main__":
    unittest.main()
