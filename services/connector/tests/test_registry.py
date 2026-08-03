"""源注册表一致性测试（C1，2026-08-02）。

H5：重复 id 与非法记录用注入样例证明加载器真的会拒绝，
不是只测「正常文件能加载」。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from campuspath_connector.registry import _REGISTRY_PATH, load_registry
from campuspath_contracts.publishing import RegisteredSource, SourceKind


class RegistryConsistency(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = load_registry()

    def test_loads_and_every_entry_validates(self) -> None:
        self.assertGreaterEqual(len(self.sources), 60)

    def test_policy_sources_never_bear_opportunities(self) -> None:
        for source in self.sources:
            if source.kind is SourceKind.POLICY_SOURCE:
                self.assertFalse(
                    source.opportunity_bearing,
                    f"{source.source_id}: 政策源只产政策提醒卡，不得标记为机会源",
                )

    def test_mock_sources_are_labeled(self) -> None:
        mock_ids = {s.source_id for s in self.sources if not s.is_real_fetch}
        # 既有五个合成机会源 + 三个合成教育连接器必须如实标 mock（用户裁定 D）
        for expected in ("SRC-career-center", "SRC-partner-ats", "SRC-lab-site",
                         "SRC-club-portal", "SRC-events-calendar", "SRC-sis",
                         "SRC-lms", "SRC-timetable"):
            self.assertIn(expected, mock_ids)

    def test_real_sources_use_http_urls(self) -> None:
        for source in self.sources:
            if source.is_real_fetch:
                self.assertTrue(
                    source.url.startswith("https://"),
                    f"{source.source_id}: 真实源必须是 https URL，得到 {source.url}",
                )
            else:
                self.assertTrue(source.url.startswith("mock://"))

    def test_direct_publish_whitelist_is_hkust_domains_only(self) -> None:
        """直发广场白名单 = HKUST 官方域名（用户裁定 A）。"""
        for source in self.sources:
            if source.official_hkust:
                host = source.url.split("//", 1)[-1].split("/", 1)[0]
                self.assertTrue(host in ("hkust.edu.hk", "ust.hk")
                                or host.endswith(".hkust.edu.hk")
                                or host.endswith(".ust.hk"))
        # 政府政策源不在直发白名单（immd.gov.hk 不是 HKUST 域名）
        immd = next(s for s in self.sources if s.source_id == "HK-IMMD-STUDY")
        self.assertFalse(immd.official_hkust)
        # HKUST 源在白名单
        urop = next(s for s in self.sources if s.source_id == "urop-projects")
        self.assertTrue(urop.official_hkust)

    def test_duplicate_id_is_rejected(self) -> None:
        """H5：构造重复 id 文件，断言加载器真的抛错。"""
        raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        raw["sources"].append(dict(raw["sources"][0]))
        with TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_registry(bad)

    def test_invalid_record_is_rejected(self) -> None:
        """H5：非法 kind 的记录必须被契约校验拒绝。"""
        raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        raw["sources"][0] = {**raw["sources"][0], "kind": "totally_bogus"}
        with TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(Exception):
                load_registry(bad)

    def test_p0_sources_match_resource_map(self) -> None:
        """资源地图 §9 的 P0 六源必须全部在册且为 p0。"""
        p0 = {s.source_id for s in self.sources if s.priority == "p0" and s.kind is SourceKind.OPPORTUNITY_SOURCE}
        for expected in ("hkust-event-calendar", "career-center-recruitment",
                         "ec-events", "cse-placement", "registry-resource-library",
                         "urop-projects"):
            self.assertIn(expected, p0)


if __name__ == "__main__":
    unittest.main()
