"""共享抓取器与变更检测测试（C2）。

H5：changed / unchanged / error 三态各用已知样例证明——
尤其是「已知会变的内容必须报 changed」「已知坏地址必须报 error」，
不是只测正常路径。全部离线（monkeypatch fetch），不发真实请求。
"""

from __future__ import annotations

import unittest
from unittest import mock

from campuspath_connector import fetcher


class NormalizeAndHash(unittest.TestCase):
    def test_script_style_and_whitespace_are_noise(self) -> None:
        a = "<html><script>var x=1;</script><body>  Hello   <b>World</b>\n</body></html>"
        b = "<html><script>var x=999;</script><body>Hello World</body></html>"
        self.assertEqual(fetcher.normalize_text(a), "Hello World")
        self.assertEqual(fetcher.content_hash(a), fetcher.content_hash(b))

    def test_visible_change_changes_the_hash(self) -> None:
        a = "<body>Deadline: 2026-08-03</body>"
        b = "<body>Deadline: 2026-09-01</body>"
        self.assertNotEqual(fetcher.content_hash(a), fetcher.content_hash(b))


class ProbeOutcomes(unittest.TestCase):
    def test_known_change_reports_changed(self) -> None:
        with mock.patch.object(fetcher, "fetch", return_value="<body>v2 content</body>"):
            old = fetcher.content_hash("<body>v1 content</body>")
            result = fetcher.probe("https://example.invalid/page", old, delay=0)
        self.assertEqual(result.outcome, "changed")
        self.assertIn("v2 content", result.text_excerpt or "")

    def test_same_content_reports_unchanged(self) -> None:
        html = "<body>steady</body>"
        with mock.patch.object(fetcher, "fetch", return_value=html):
            result = fetcher.probe("https://example.invalid/page", fetcher.content_hash(html), delay=0)
        self.assertEqual(result.outcome, "unchanged")

    def test_first_probe_without_history_is_changed(self) -> None:
        with mock.patch.object(fetcher, "fetch", return_value="<body>first sight</body>"):
            result = fetcher.probe("https://example.invalid/page", None, delay=0)
        self.assertEqual(result.outcome, "changed")

    def test_known_bad_url_reports_error_not_raise(self) -> None:
        """H5：真实访问一个已知不可达地址（.invalid TLD 保证解析失败）。"""
        result = fetcher.probe("https://does-not-exist.invalid/", None, delay=0)
        self.assertEqual(result.outcome, "error")
        self.assertIsNotNone(result.detail)


if __name__ == "__main__":
    unittest.main()
