""":class:`EducationDataAdapter` 的 Moodle 实现。

只实现 Moodle **真正承载**的数据：学生选了什么课（enrolments）。
培养方案、Degree Audit、开课时刻表不在 Moodle 里——这三个方法
如实返回空列表，由组合层与 Mock SIS 合并，**不在这里编造**。

身份映射：CampusPath 的 ``STU-A`` ↔ Moodle 用户名 ``stu-a``；
课程码：Moodle shortname ``COMP1021`` ↔ 目录码 ``COMP 1021``。
两条映射都是确定性字符串变换，写在这里一处。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from campuspath_contracts.academic import (
    CourseCatalogItem,
    CourseOffering,
    CourseStatus,
    DegreeRequirement,
    RecordSource,
    StudentCourseRecord,
)

from .client import MoodleClient

_SHORTNAME = re.compile(r"^([A-Z]{4})(\d{4}[A-Z]?)$")


def moodle_username(student_id: str) -> str:
    return student_id.lower().replace("stu-", "stu-")


def course_code(shortname: str) -> str | None:
    match = _SHORTNAME.match(shortname.strip().upper())
    if match is None:
        return None
    return f"{match.group(1)} {match.group(2)}"


class MoodleEducationAdapter:
    def __init__(self, client: MoodleClient, *, term: str) -> None:
        self._client = client
        self._term = term

    def course_records(self, student_id: str) -> list[StudentCourseRecord]:
        username = moodle_username(student_id)
        users = self._client.call(
            "core_user_get_users_by_field", field="username", values=[username],
        )
        if not users:
            return []
        courses = self._client.call(
            "core_enrol_get_users_courses", userid=users[0]["id"],
        )
        now = datetime.now(timezone.utc)
        records: list[StudentCourseRecord] = []
        for course in courses:
            code = course_code(course.get("shortname", ""))
            if code is None:
                continue        # 非课程类站点（如首页）不伪装成选课记录
            records.append(StudentCourseRecord(
                record_id=f"MDL-{student_id}-{code.replace(' ', '')}",
                student_id=student_id,
                course_id=code,
                term=self._term,
                # Moodle 只知道"注册着"；成绩与学分是 SIS 的事，不越权猜——
                # credits=0 + grade_scope 默认 not_released 都是"不知道"，不是 0 分
                status=CourseStatus.ENROLLED,
                credits=0.0,
                source=RecordSource.LMS,
                updated_at=now,
            ))
        return records

    def degree_requirements(self, program_id: str) -> list[DegreeRequirement]:
        """Moodle 不承载培养方案——如实返回空，组合层去问 Mock SIS。"""
        return []

    def catalog(self, subject: str | None = None) -> list[CourseCatalogItem]:
        """课程目录的权威来源是 HKUST 公开目录快照，不是 Moodle。"""
        return []

    def offerings(self, term: str) -> list[CourseOffering]:
        return []
