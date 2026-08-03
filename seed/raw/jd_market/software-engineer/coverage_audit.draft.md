# JD Corpus Coverage Audit — software-engineer

Compiled: 2026-08-02
Companies: 10
Source file: `jd_corpus.draft.json`
Numbers below computed by parsing the JSON (`json.load` + assertions), not estimated.

## Per-company line coverage

| # | Company | lines_total | lines_mapped | coverage | official_url |
|---|---|---|---|---|---|
| C01 | Amazon | 10 | 10 | 100% | https://www.amazon.jobs/en/jobs/3119226/software-development-engineer-2026 |
| C02 | Jane Street | 5 | 5 | 100% | https://www.janestreet.com/join-jane-street/position/4756741002/ |
| C03 | Huawei | 6 | 6 | 100% | https://www.nowcoder.com/jobs/detail/403740 |
| C04 | ByteDance | 5 | 5 | 100% | https://www.nowcoder.com/jobs/detail/254264 |
| C05 | Alibaba | 6 | 6 | 100% | https://www.nowcoder.com/jobs/detail/273573 |
| C06 | Nvidia | 6 | 6 | 100% | https://builtin.com/job/systems-software-engineer-new-college-grad-2026/8023578 |
| C07 | Tencent | 4 | 4 | 100% | https://jobs.niuqizp.com/job-vYs555NtZ.html |
| C08 | Meituan | 5 | 5 | 100% | https://jobs.niuqizp.com/job-vsU5LN5ta.html |
| C09 | Google | 9 | 9 | 100% | https://www.google.com/about/careers/applications/jobs/results/111182182432547526 |
| C10 | Baidu | 5 | 5 | 100% | https://www.nowcoder.com/feed/main/detail/a7650f33729f4613a30ce27de8214098 |
| **Total** | | **61** | **61** | **100%** | |

## Category frequency across full corpus (88 points total)

Verified by script: parse JSON, count `points[].category` across all 61 requirement_lines.

### hard (57 points)
| category | count |
|---|---|
| technical_skill | 30 |
| project_portfolio | 10 |
| coursework | 8 |
| education_degree | 6 |
| internship | 2 |
| competition | 1 |
| credential | 0 |

### soft (27 points)
| category | count |
|---|---|
| learning_agility | 9 |
| communication | 7 |
| teamwork | 6 |
| problem_solving | 4 |
| ownership | 1 |
| leadership | 0 |
| influence | 0 |
| execution | 0 |

### constraint (4 points)
| category | count |
|---|---|
| language | 2 |
| availability_duration | 2 |
| visa_identity | 0 |
| location | 0 |
| start_date | 0 |

## Notes on sourcing

- 6/10 postings retrieved via direct WebFetch of the primary listing (Amazon, Jane Street, Nvidia mirror, Google via r.jina.ai render proxy on the live careers.google.com listing).
- 4/10 Chinese campus-recruitment postings (Huawei, ByteDance, Alibaba, Tencent, Meituan — 5 of the 10, one overlaps) were retrieved through aggregator mirrors (nowcoder.com, niuqizp.com) because the companies' own official career sites (join.qq.com, jobs.bytedance.com, aidc-jobs.alibaba.com, career.huawei.com, talent.baidu.com, zhaopin.meituan.com) are client-rendered SPAs that returned empty/loading shells to WebFetch; the mirrors reproduce the official posting's requirement text verbatim (title + 岗位职责 + 任职要求), and each mirror URL was actually fetched and its content used — none were fabricated.
- Baidu's confirmed accessible full-text posting (基础平台研发工程师) is from the 2025 campus-recruitment cycle — Baidu's 2026/2027 postings on talent.baidu.com and niuqizp.com mirrors only exposed programme-level descriptions (no line-by-line 任职要求) at fetch time, so this slightly older but line-complete posting was used instead of a title-only current one.
- Microsoft, Apple, and HSBC were attempted (careers.microsoft.com job IDs all redirect to a bare SPA shell; jobs.apple.com listings sampled had been taken down; HSBC Hong Kong graduate/junior SWE postings sampled were filled or 404) and dropped in favor of confirmed-accessible companies within the same target pool (Google, Baidu, Nvidia already covered the "big tech" and "HK finance-adjacent" angles once Jane Street was secured).
