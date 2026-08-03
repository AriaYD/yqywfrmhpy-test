# JD Corpus Coverage Audit — ui-ux-designer

Compiled: 2026-08-02
Companies: 8 (target was 10; 8 delivered — see "Sourcing gaps" below for what was tried and dropped, per "宁少勿假")
Source file: `jd_corpus.draft.json`
Numbers below computed by parsing the JSON (`json.load` + assertions), not estimated. Self-check output is reproduced verbatim at the bottom of this file.

## Per-company line coverage

| # | Company | lines_total | lines_mapped | coverage | official_url |
|---|---|---|---|---|---|
| C01 | Google | 7 | 7 | 100% | https://www.google.com/about/careers/applications/jobs/results/87880344878883526-ux-designer-tools-automation-and-infrastructure/ |
| C02 | Tencent | 7 | 7 | 100% | https://careers.tencent.com/jobdesc.html?postId=2070157576028471296 |
| C03 | HSBC | 8 | 8 | 100% | https://apply.careers.hsbc.com/job/Kowloon-City-Senior-Product-Designer-International-Wealth-and-Premier-Banking-Kowl/1366640057/ |
| C04 | Autohome (汽车之家) | 3 | 3 | 100% | https://www.nowcoder.com/jobs/detail/183836 |
| C05 | miHoYo (米哈游) | 3 | 3 | 100% | https://www.nowcoder.com/feed/main/detail/8e7527ba06f44a4893b0d98015fda46c |
| C06 | 九方云 | 6 | 6 | 100% | https://job.ncss.cn/student/jobs/Tsdm5daB9xXKsC76st1AyZ/detail.html |
| C07 | JD.com (京东) | 3 | 3 | 100% | https://www.liepin.com/job/1933370961.shtml |
| C08 | Meituan (美团) | 5 | 5 | 100% | https://www.liepin.com/job/1958931851.shtml |
| **Total** | | **42** | **42** | **100%** | |

All `requirement_lines` come from the posting's 任职要求 / "Minimum & Preferred Qualifications" / "To be successful you will need" section only (candidate-facing requirement statements) — 岗位职责/Responsibilities bullets were deliberately excluded, matching the convention already used in `software-engineer/jd_corpus.draft.json`.

## URL retrieval method and live-reachability status (tested 2026-08-02)

| # | Company | Retrieval method | Reachability status |
|---|---|---|---|
| C01 | Google | Direct `curl` fetch of the live careers.google.com job page; the page embeds all currently-open listings as JSON inside `AF_initDataCallback` blocks. Verified the block keyed to job ID `87880344878883526` (matched by the ID string appearing inside its own JSON payload, alongside `"UX Designer, Tools Automation and Infrastructure"` and location `Hyderabad, Telangana, India`) before extracting text — this guards against accidentally reading a neighboring job's data, which happened on a first pass (see gaps below). | 200 OK, page live, job open |
| C02 | Tencent | `careers.tencent.com/jobdesc.html?...` itself is a client-rendered shell (confirmed empty, ~2KB) with no server-side text. Tencent's own public recruitment JSON API (`careers.tencent.com/tencentcareer/api/post/ByPostId?postId=...`), which is what that HTML page calls client-side to render itself, was queried directly and returned the full `Responsibility`/`Requirement`/`ImportantItem` fields for this exact PostId. The `official_url` recorded is the canonical human-facing URL for this PostId. | API returns `IsValid` for this listing; `LastUpdateTime` 2026年07月03日 |
| C03 | HSBC | Direct `curl` fetch of `apply.careers.hsbc.com` (SAP SuccessFactors career site) — this domain serves full server-rendered job description text without JS execution. | 200 OK, page live ("Date: 15 Jul 2026", location Kowloon City, HK) |
| C04 | Autohome | WebFetch of `nowcoder.com/jobs/detail/183836` — full 岗位职责/任职要求 rendered server-side. | 200 OK. Note: this specific posting is labeled "2023应届校招" (2023 cycle) — it is the one full-text, line-complete UI designer posting found on this domain after multiple search attempts; more recent Autohome design postings found in search snippets lacked accessible full text. |
| C05 | miHoYo | WebFetch of `nowcoder.com/feed/main/detail/8e7527ba06f44a4893b0d98015fda46c` — full text rendered server-side, explicitly labeled "2026届" (targets Sept 2025–Aug 2026 graduates). | 200 OK, page live |
| C06 | 九方云 | WebFetch of `job.ncss.cn` (国家大学生就业服务平台, official MOE-run graduate employment platform) — full text rendered server-side. Not on the original candidate-company list (腾讯/字节/阿里/… ) — included as an honest substitute per the task's own guidance to prefer companies whose JD text is actually readable over padding with unreachable big names. | 200 OK, page live |
| C07 | JD.com | Direct `curl` fetch of `liepin.com/job/1933370961.shtml` (猎聘, a licensed recruitment platform) — full text rendered server-side, includes posting company "京东集团" verified in page title and company-info block, salary 25-35k·14薪, "90天前更新". Not on the original candidate list — substituted after Tencent's own QQ-interaction-designer Liepin mirror (`liepin.com/job/1973749333.shtml`) turned out to be closed ("该职位已暂停招聘", no body text) and was dropped. | 200 OK, page live, listing active |
| C08 | Meituan | Direct `curl` fetch of `liepin.com/job/1958931851.shtml` — full text rendered server-side, posting company "美团" verified in page title and recruiter's company field, "90天前更新". | 200 OK, page live, listing active |

## Category frequency across full corpus (67 points total, 42 requirement_lines)

Verified by script: parse JSON, count `points[].category` across all 42 requirement_lines.

### hard (35 points)
| category | count |
|---|---|
| technical_skill | 25 |
| education_degree | 5 |
| project_portfolio | 4 |
| internship | 1 |
| coursework | 0 |
| gpa | 0 |
| competition | 0 |
| credential | 0 |

### soft (31 points)
| category | count |
|---|---|
| teamwork | 7 |
| communication | 4 |
| ownership | 4 |
| user_empathy | 4 |
| learning_agility | 4 |
| data_sense | 3 |
| leadership | 2 |
| execution | 2 |
| problem_solving | 1 |
| influence | 0 |

### constraint (1 point)
| category | count |
|---|---|
| language | 1 |
| visa_identity | 0 |
| location | 0 |
| availability_duration | 0 |
| start_date | 0 |

Note on category distribution: this role's corpus skews harder toward `technical_skill` (Figma/design-tool/UX-method proficiency dominates almost every posting) and lighter on `constraint` categories, since none of the 8 accessible postings stated explicit visa/location/start-date/duration constraints in their requirement text (HSBC and Google postings did specify locations, but as job metadata rather than a candidate-facing constraint sentence, so no `location` point was manufactured from it).

## Sourcing gaps and substitutions (honest account)

Target was 10 companies from the suggested pool (腾讯/字节跳动/阿里巴巴/网易/小米/美团/百度/华为/快手/微软/Google/Apple/Booking/Grab/Shopee/HSBC/Klook). **8 were delivered.** What was tried and why the other candidates were dropped instead of padded with unverifiable content:

- **ByteDance (字节跳动)**: `jobs.bytedance.com` job-search pages and API endpoints all returned redirects/empty shells; no reachable full-text UI/UX posting found via search-engine mirrors either (nowcoder/BOSS listings surfaced only sold-out or "loading" shells). Dropped.
- **Alibaba (阿里巴巴)**: `job.alibaba.com/zhaopin/PositionDetail.htm` (old positionId 84953 and 13144) both 302-redirect to the `talent.alibaba.com` homepage (expired listings); `talent.alibaba.com` and `campus-talent.alibaba.com` are pure client-rendered SPAs with no embedded job JSON reachable via plain `curl`; company-specific Liepin/nowcoder mirrors surfaced only tangential postings (智慧园区设计咨询专家, 动画设计实习生) that are not UI/UX designer roles. Dropped.
- **NetEase (网易)**: `campus.game.163.com` is a pure client-rendered SPA shell; no reachable full-text UI/UX posting found. Dropped.
- **Xiaomi (小米)**: `hr.xiaomi.com/campus/list/5-0-0` (campus, design category filter) genuinely returned zero open positions at fetch time ("对不起，该条件下没有职位"). A social-recruit Liepin listing for a Xiaomi 高级用户体验设计师 was found closed ("该职位已暂停招聘"); a 小米汽车 视觉设计师 listing was referenced in search snippets but no working direct URL could be resolved. Dropped.
- **Baidu (百度)**: `talent.baidu.com` API requires authenticated session (`{"status":"no-auth"}`); Baidu's dedicated Liepin recruitment page (`liepin.com/zpbaidu/`) was fetched and scanned — none of its ~20 currently-listed postings are design roles at fetch time. Dropped.
- **Huawei (华为)**: `career.huawei.com` campus API endpoints guessed did not resolve (404); a gaoxiaojob.com mirror of an ID/UX designer posting was found but explicitly stated "已下线" (delisted) with body text replaced by "详见公告正文" (no actual requirement text present). Dropped.
- **Kuaishou (快手)**: one Liepin mirror (`job/1976024141.shtml`, 高级产品设计师) was fetched but was closed ("该职位已暂停招聘", no body text). No other reachable full-text posting found. Dropped.
- **Microsoft**: `careers.microsoft.com` job pages and the `gcsservices.careers.microsoft.com` search API were both unreachable in this environment (TLS certificate for the resolved IP did not match the hostname — an environment-level network-path issue, not evidence the real site is broken, but it means the content could not be *verified reachable by this agent*, so it was not used). Dropped.
- **Apple**: `jobs.apple.com/en-us/details/...` pages returned only localization-string JSON via `curl`/WebFetch, not the actual job-description JSON (Apple's job data loads via a separate authenticated-looking XHR that could not be located). Dropped.
- **Grab**: `grab.careers` job pages returned HTTP 403 from an Azure WAF on both WebFetch and `curl`. Dropped.
- **Shopee**: `careers.shopee.sg/job-detail/*` is a pure client-rendered shell (confirmed via `curl`, 3.5KB, no embedded data); guessed API paths 404'd. Dropped.
- **Klook**: `klookcareers.com` redirects into a Moka-style recruiting SaaS page that returned a >10-redirect loop under WebFetch and only JSON API error stubs under `curl` guesses. Dropped.
- **Booking.com**: `careers.booking.com` returned HTTP 403; `jobs.booking.com` 301-redirected to a dead path. Dropped.

**Self-correction during sourcing**: the first `curl` fetch of a Google UX Designer job ID (`73079247123423942`, and three others sourced from stale WebSearch snippets) all resolved to Google's generic "Jobs search" page rather than the specific listing — meaning those job IDs had expired and the site fell back to a search results page whose embedded JSON happened to contain *other* jobs' data (e.g., a YouTube Strategy Associate posting was almost mis-attributed as "Google UX Designer" content on a first, too-hasty read). This was caught by checking the page `<title>` (must read "UX Designer..." not "Jobs search") and by re-deriving live job IDs from Google's own current search-results page (`.../jobs/results/?q=UX%20Designer`) before re-fetching. The Google entry used in the corpus (`87880344878883526`) was verified by finding its exact job-ID string inside its own JSON block, immediately adjacent to its stated title and location, before any text was extracted.

## Self-check script output (reproduced verbatim)

```
JSON parsed OK. role = ui-ux-designer compiled_at = 2026-08-02
companies: 8
total requirement_lines: 42
total points: 67
duplicate line_ids: []
duplicate point_ids: []
companies with empty requirement_lines: []
bad layer/category combos: []
all categories used are within vocab: True

layer counts: {'hard': 35, 'soft': 31, 'constraint': 1}
category counts: {'education_degree': 5, 'technical_skill': 25, 'teamwork': 7, 'leadership': 2, 'communication': 4, 'execution': 2, 'ownership': 4, 'user_empathy': 4, 'project_portfolio': 4, 'language': 1, 'learning_agility': 4, 'problem_solving': 1, 'internship': 1, 'data_sense': 3}

Per-company line/point counts:
  Google       lines=7, points=8, url=https://www.google.com/about/careers/applications/jobs/results/87880344878883526-ux-designer-tools-automation-and-infrastructure/
  Tencent      lines=7, points=11, url=https://careers.tencent.com/jobdesc.html?postId=2070157576028471296
  HSBC         lines=8, points=9, url=https://apply.careers.hsbc.com/job/Kowloon-City-Senior-Product-Designer-International-Wealth-and-Premier-Banking-Kowl/1366640057/
  Autohome     lines=3, points=6, url=https://www.nowcoder.com/jobs/detail/183836
  miHoYo       lines=3, points=6, url=https://www.nowcoder.com/feed/main/detail/8e7527ba06f44a4893b0d98015fda46c
  九方云          lines=6, points=11, url=https://job.ncss.cn/student/jobs/Tsdm5daB9xXKsC76st1AyZ/detail.html
  JD.com       lines=3, points=7, url=https://www.liepin.com/job/1933370961.shtml
  Meituan      lines=5, points=9, url=https://www.liepin.com/job/1958931851.shtml
```
