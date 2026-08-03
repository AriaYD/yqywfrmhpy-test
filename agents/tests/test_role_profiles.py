"""岗位画像回归（A，2026-08-02）：编译产物 → A3 确定性消费。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from campuspath_agents.model import ScriptedModel
from campuspath_agents.roster import (
    GoalGapAgent, _employment_role_profiles, _match_role_profile,
)
from campuspath_agents.tools import belt_for
from campuspath_contracts.common import AgentId, DevelopmentModeType
from campuspath_contracts.goals import Goal

NOW = datetime(2026, 8, 2, 9, tzinfo=timezone.utc)


def goal(target_name: str, mode=DevelopmentModeType.EMPLOYMENT) -> Goal:
    return Goal(goal_id="G-RP", student_id="STU-A", development_mode=mode,
                target_type="role", role="primary", target_name=target_name,
                horizon="long_term", confidence=0.8, status="active",
                last_reviewed=NOW, created_at=NOW)


def a3() -> GoalGapAgent:
    return GoalGapAgent(AgentId.A3_GOAL_GAP,
                        belt_for(AgentId.A3_GOAL_GAP, {}), ScriptedModel())


class RoleProfiles(unittest.TestCase):
    def test_compiled_profiles_exist_and_have_market_evidence(self):
        profiles = _employment_role_profiles()
        self.assertEqual(set(profiles), {"ai-product-manager", "software-engineer"})
        for key, profile in profiles.items():
            cores = [f for f in profile["facets"] if f.priority == "core"]
            self.assertGreaterEqual(len(cores), 5, key)
            for facet in profile["facets"]:
                self.assertIsNotNone(facet.market_note,
                                     f"{key}: 每条画像 facet 必须带市场证据数字")
                self.assertIn("JD", facet.market_note.zh_Hans)

    def test_target_name_matching_is_deterministic(self):
        self.assertEqual(_match_role_profile(goal("毕业后成为 AI 产品经理"))[0],
                         "ai-product-manager")
        self.assertEqual(_match_role_profile(goal("Software Engineer, Google"))[0],
                         "software-engineer")
        self.assertIsNone(_match_role_profile(goal("咨询顾问"))[0])

    def test_domain_qualifier_blocks_substring_hijack(self):
        """审计红-2（2026-08-02）：「游戏开发工程师」曾被「开发工程师」子串
        劫持成 SWE 画像——领域修饰词紧贴关键词时必须判为不同岗位、回落
        现场拆解；资历/志向类中性前缀不受影响。"""
        self.assertIsNone(_match_role_profile(goal("游戏开发工程师"))[0])
        self.assertIsNone(_match_role_profile(goal("Game Developer"))[0])
        self.assertIsNone(_match_role_profile(goal("硬件产品经理"))[0])
        # 中性前缀（资历/志向）不改变岗位本体，照常命中
        self.assertEqual(_match_role_profile(goal("资深软件工程师"))[0],
                         "software-engineer")
        self.assertEqual(_match_role_profile(goal("毕业后成为产品经理"))[0],
                         "ai-product-manager")
        self.assertEqual(_match_role_profile(goal("后端工程师"))[0],
                         "software-engineer")

    def test_decompose_uses_role_profile_and_falls_back(self):
        hit = a3().decompose_goal(goal("AI 产品经理"))
        self.assertEqual(hit.role_profile, "ai-product-manager")
        self.assertTrue(any(f.priority == "core" for f in hit.facets))
        # 约束层占位仍在（intl Pack 未加载时的待确认条目）
        self.assertTrue(any(f.kind == "constraint" for f in hit.facets))

        miss = a3().decompose_goal(goal("咨询顾问"))
        self.assertIsNone(miss.role_profile)
        self.assertTrue(all(f.priority == "standard" for f in miss.facets),
                        "通用 Pack 没有市场加权，不该出现 core")

    def test_non_employment_modes_untouched(self):
        deco = a3().decompose_goal(goal("攻读 NLP 方向硕士",
                                        DevelopmentModeType.ACADEMIA))
        self.assertIsNone(deco.role_profile)
        self.assertTrue(all(f.market_note is None for f in deco.facets))


if __name__ == "__main__":
    unittest.main()


class IndustryModifierRecall(unittest.TestCase):
    def test_industry_modifiers_do_not_block(self):
        """审查 M11：行业/载体修饰不改变岗位本体——不许把召回打没。"""
        self.assertEqual(_match_role_profile(goal("互联网产品经理"))[0],
                         "ai-product-manager")
        self.assertEqual(_match_role_profile(goal("嵌入式软件工程师"))[0],
                         "software-engineer")
        # 领域修饰仍然阻断（红-2 的修复目标不回退）
        self.assertIsNone(_match_role_profile(goal("游戏开发工程师"))[0])
