# manual_isom_ieda.json — 转录说明

人工转录（读取官方 PDF/网页内容后手动整理为 JSON），非爬虫产出，未经与 PDF 的二次自动比对校核。

## 来源 URL

- ISOM / BBA in Information Systems
  - 官方课程要求 PDF（2025-26 入学年度）：https://isom.hkust.edu.hk/sites/isom/files/2025-09/25-26is.pdf
  - Curriculum 页面（提供 PDF 链接列表，含历年 cohort）：https://isom.hkust.edu.hk/programs-n-courses/ug-programs/bba-in-is/curriculum
  - Overview 页面：https://isom.hkust.edu.hk/programs-n-courses/ug-programs/bba-in-is/overview
- IEDA / BEng in Industrial Engineering and Engineering Management (IEEM)
  - 官方课程要求 PDF（2025-26 入学年度）：https://ugadmin.hkust.edu.hk/prog_crs/ug/202526/pdf/25-26ieem.pdf
  - IEDA 系官网课程页（列出各 cohort PDF 链接）：https://ieda.hkust.edu.hk/eng/detail.php?catid=3&sid=64&tid=90
  - 对照用旧版（2019-20 入学年度，仅用于核对电子工程选项是否变化，未写入 JSON 主体）：https://ugadmin.hkust.edu.hk/prog_crs/pdf/ug/ieem.pdf

两个 PDF 都取的是当前可查到的**最新 cohort（2025-26 入学）**版本，与 programs.json 里 COMP 条目所用的年份基准（2026-27）不完全一致——HKUST 官网当前尚未发布 IS / IEEM 的 2026-27 版本 PDF，2025-26 是官方页面上能抓到的最新版本。

## 转录统计

- ISOM：4 个 requirement_groups，共 9 门课程代码
  - Required Course(s)：ISOM 3210, 3260, 3320, 3400（4 门，其中 3320/3400 为 OR 二选一）
  - 3 个 Option（Financial Engineering / Information Systems Auditing / Business Analytics），共 5 门课程代码
- IEDA：6 个 requirement_groups，共 49 门课程代码（含跨系 COMP/CHEM/PHYS/MATH/ECON/FINA/ISOM/RMBI 课程代码）
  - Engineering Fundamental Course(s)：13 门（COMP/CHEM/PHYS/MATH 各子条件 OR 逻辑）
  - Required Course(s)：16 门（含 IEDA 4901/4960 OR、ECON 2103/2113 OR）
  - Elective(s)：12 门（Industrial Engineering Electives，最低 21 学分）
  - 3 个 Option（Financial Engineering 必修+选修 / Research 选修），共 8 门课程代码

## 官方页面没有给出、因此未写入 JSON 的信息

1. **ISOM 的 IS Electives 具体课程清单**——官方 PDF 只写"任选 3 门 ISOM 课程，学分合计 ≥10，课号介于 3000-3499 或 4000-4499 之间"，是一个**按课号范围筛选的规则**，不是封闭课程清单。要还原完整清单需要额外抓取 ISOM 系全部本科课程目录（课号 3000-4499 区间），逐一核对哪些课程当前学年实际开设，这超出本次手动转录范围，因此按任务要求**未写入该 requirement_group**。
2. **两个专业的 total_credits_required 和 university_graduation_requirements 是否与 BBA-IS / IEEM 专属页面完全一致**——PDF 正文没有单独重复"总学分 120"这类大学层面通用信息（只在开头引用式提及需满足大学毕业要求），JSON 里这部分是复用 programs.json 中 COMP 条目已有的通用大学基线数值，**未针对这两个专业单独在官方页面上重新确认**。
3. **IEDA 系是否仍保留 2019-20 版 PDF 中的 Group 1/Group 2/Group 3（Engineering Management / Logistics Management / Other）三分组选修结构，以及"至少 15 学分出自其中一个方向、至少 6 学分出自方向外"的规则**——2025-26 版 PDF 里 Elective(s) 已经改成扁平化的单一课程清单，没有再区分方向分组或方向内学分下限，JSON 按 2025-26 版本如实转录，2019-20 版本的分组规则未沿用。
4. **Research Option 选修清单里的 IEDA 5260**——曾出现在 2019-20 版 PDF（Deterministic Models in Operations Research 之外还有 Design and Analysis of Engineering Experiments, IEDA 5260），2025-26 版 PDF 该 Option 的选修清单只剩 3 门（IEDA 4900 / 5170 / 5230），IEDA 5260 未出现。不确定是课程停开、改代码还是版面截断，未核实，已在 JSON 对应 group 的 notes 字段标注。
5. **BBA-IS 的 School Requirements（商学院层面的额外通识/共同必修要求）PDF**——官方页面有另外的 School Requirements 板块，本次未抓取其对应 PDF，JSON 中 `source_urls.school_requirements_pdf` 留空为 null。
6. **IEDA 系官方全称的中文名 / ISOM 系官方全称的中文名**——本次转录只确认了英文全称（Department of Industrial Engineering and Decision Analytics；Department of Information Systems, Business Statistics and Operations Management），未额外核实中文官方译名。

## 抓取方式说明

两份 PDF 均通过 `curl` 直接下载后用 Read 工具做 PDF 文本抽取，逐条与截图版式核对课程代码与学分数字后手动整理进 JSON（而非用脚本自动解析表格），因此严格意义上进行了一次 PDF 内容核对，但未做机器可重复的二次校验脚本，`provenance.note` 按任务要求统一标注为"人工转录自官方公开页面，未经 PDF 校核"。
