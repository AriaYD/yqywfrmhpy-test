# HKUST 五专业按学期修读计划 — 数据说明

生成日期：2026-07-31。数据文件：`seed/raw/hkust_programs/term_plans.json`。

## 通用方法论

HKUST 官方 major requirement PDF（`_cache/major_<PROG>.txt` 为其 OCR 文本缓存）**不提供
逐学期（Y1_FALL ... Y4_SPRING）的课程排布**，只给出必修组、选修组及组内的 OR/AND 替代逻辑
（例如 "MATH 2111 OR MATH 2121 OR MATH 2131"）。因此本数据集对每个专业都标注
`"source": "mixed"`：

- **课程清单本身**（必修组的课程码、组内 OR/AND 逻辑）100% 来自官方 PDF 原文
  （`_cache/major_<PROG>.txt` 保留了 `programs.json` 扁平化时丢失的组内 Note 结构）。
- **逐学期的排布顺序**是推断：按课程编号首位数字对应年级（1000→Y1、2000→Y2、3000→Y3、
  4000→Y4），并结合已知先修链（如 COMP2011 先于 COMP2012，COMP2611/2711 先于
  COMP3511/3711）来决定 Fall / Spring。

**"择一逻辑组"的处理**：凡是 `programs.json` 中 `type: "required"` 但代表"互斥选项"的组
（如同一门课的荣誉版 vs 普通版、多个 Track 中选一个、多个 Option 中选一个、或"从 N 门课中选
 M 门"的 School Requirements），整组课程码被放入同一学期，并在该学期 `notes` 字段中用中文
说明"实际只需其中一条路径/一门课"。这是刻意的设计选择，用来满足"该专业必修组的课程码必须
全部出现在某个学期"这一要求，同时不误导使用者以为这些课程要同时全部修读。

**已知数据源问题**：`programs.json` 中 COMP 的 Required Course(s) 组包含一个不存在的课程码
`MATH 2540`。核对 `_cache/major_COMP.txt` 第 92-93 行原文：

```
92   ELEC/IEDA/    Note: ELEC 2600 OR ELEC 2600H OR IEDA 2520 OR IEDA
93   MATH          2540 OR MATH 2411 OR MATH 2421 OR MATH 2431
```

PDF 表格换行把 "IEDA 2540" 拆成了 "IEDA"（上一行）+ "2540"（下一行前缀被误认成属于下一行的
"MATH" 列），OCR/解析脚本因此生成了一个从未存在过的 "MATH 2540"。交叉核对
`seed/raw/hkust_catalog/courses.json`（1534 门课程的官方目录快照）确认不存在该课程码，真实课程
是 `IEDA 2540`（已正确出现在 `programs.json` 里）。本数据集**未**将 `MATH 2540` 排入任何学期，
建议后续修正 `programs.json` 抓取脚本本身。

---

## COMP（BEng Computer Science）

**来源**：官方 PDF `https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27comp.pdf`
（Engineering Fundamental 9 门代码 + Required Course(s) 24 门代码，扣除上述 `MATH 2540`
伪影后共 33 个有效必修代码，全部排入 8 个学期）。

- Y1：Python(COMP1023) + 微积分路径（1013+1014 或 1023+1024 或单学期 1020）。
- Y2：C++/OOP(2011→2012，或直接 2012H)、计算机组成(2611)、离散数学(2711/2711H)、线性代数
  (2111/2121/2131 三选一)。
- Y3：操作系统(3511)、算法(3711/3711H)、概率课(ELEC2600 系/IEDA2520/2540/MATH2411/2421/2431
  七选一)、软件工程(3111/3111H)。
- Y4：毕业路径三选一 —— 实习(1991)+毕设(4981/4981H)，或带薪实习项目(4910)。
- Elective(s)：COMP 2000+ 选修 1 门(3学分) + COMP Electives 5 门(15学分，≥3门同领域+≥2门
  跨领域)，未逐一列入学期，见 JSON 中 `elective_requirement` 字段。

## CENG（BEng Chemical Engineering）

**来源**：官方 PDF `https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27ceng.pdf`
（Engineering Fundamental 10 门 + Required Course(s) 25 门 + Environment Option
Required 1 门(ENEG1700)，共 36 个必修代码全部排入）。

- Y1：编程四选一 + 化学(1012/1052) + 微积分三选一(单学期) + 物理二选一 + 生物基础三选一
  + CENG 入门课(1000/1010/1110)。
- Y2-Y3：CENG 核心序列（热力学→输运→建模→分离过程→反应工程→数据科学→控制），有机化学
  (2111/2155)。
- Y4：毕业设计三选一(4920 设计 / 4930 论文 / 4940 工业项目)、Integrated Design(3150)、
  APD II(4020)。
- ENEG1700 仅 Environment Option 学生需修（该 Option 可选），列入 Y4_SPRING 并注明。
- Elective(s)：12 学分自 CENG/BIEN/COMP/ENEG/CHEM 列表；Environment Option 另需
  3 学分/1 门，未逐一列入学期。

## MATH（BSc Mathematics）

**来源**：官方 PDF `https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27math.pdf`。
MATH 是五个专业中结构最复杂的：Major Pre-requisite(5 门) + Required Course(s)(8 门，均为
普通版/荣誉版二选一) 之后，学生须在 **6 个 Track**（Applied Mathematics / Computer Science /
Financial and Actuarial Mathematics / General Mathematics / Pure Mathematics /
Pure Mathematics (Advanced)）与 International Research Enrichment(IRE) Track 之间
选择一个，每个 Track 各有自己的 Required Course(s) 组（`programs.json` 中同样标记为
`type: "required"`）。

**本表的处理方式**：

1. Y1-Y3_FALL：Major Pre-requisite + 全专业共同 Required Course(s)（微积分/线性代数/分析，
   均含普通版/荣誉版二选一），这部分所有 MATH 学生都要修，按学期正常排布。
2. **主线示例**：选用 **Applied Mathematics Track**（较通用的应用数学方向）作为 Y3_SPRING
   -Y4_SPRING 的示范路径，按其 Required Course(s) 顺序排布（微分方程→应用统计→数值分析→
   偏微分方程→数学建模→毕业设计）。
3. **其余 5 个 Track + IRE 的 Required Course(s)**：与主线互斥（学生只能选一个 Track），
   但其课程码仍需"全部出现在某个学期"，因此整组作为"备选 Track"附加列入 Y3_SPRING /
   Y4_FALL / Y4_SPRING 的 `required` 数组，并在该学期 `notes` 字段中用【备选 Track】标签
   逐一说明每组课程属于哪个 Track、彼此互斥、不与主线同修。
4. **School Requirements**（理学院共同要求，43 门课选 6 门、每学科至多 3 门）在
   `programs.json` 中同样标记为 `type: "required"`，但本质是与 Major Prerequisite/Required
   大量重叠的组合选修（如 MATH1013/1014、MATH2121、CHEM/PHYS 基础课）。整组列入 Y1_SPRING，
   `notes` 中说明其"组内选修"性质，不代表额外新增约 37 门课的学分负担。

MATH 的 `elective_requirement` 字段按 Track 分别摘录（每个 Track 的选修学分/门数要求不同）。

## MECH（BEng Mechanical Engineering）

**来源**：官方 PDF `https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27mech.pdf`
（Engineering Fundamental 16 门 + Required Course(s) 22 门 + Research Option Required
1 门(MECH4995)，共 39 个必修代码全部排入）。

- Y1：编程三选一 + 微积分路径(同 COMP/CENG，五门代码) + 物理二选一 + Science 1000-level
  四选一(CHEM1008/CHEM1012/LIFS1901/PHYS1101)。
- Y2：多元微积分(2011)、微分方程(2351)、静力学/动力学(2020)、固体力学(2040)、流体力学
  (2210)、工程计算(2300)、热力学(2310)、材料 I(2410)、设计与制造 I(2520)。
- Y3：机构学(3030)、控制原理(3610)、电气技术(3630)、基础电子(ELEC2420)、
  3300/3420/3710 三选一（能源转换/材料II/制造工艺）、传热学(3310)、实验室(3830)、
  机电一体化设计(3907)。
- Y4：毕业设计(4900，全年制 6 学分)；Research Option 的 MECH4995 仅该 Option 学生需修，
  列入 Y4_SPRING 并注明。
- Energy / Engineering Design / Materials 三个 Option 均为可选方向电(各 9 学分/3门)，
  未逐一列入学期，见 `elective_requirement`。

## BCB（BSc Biochemistry and Cell Biology）

**来源**：官方 PDF `https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27bcb.pdf`。
Major Pre-requisite(2 门) + Required Course(s)(24 门) + IRE Track Required(3 门) +
School Requirements(43 门，与 MATH 共享同一份理学院共同要求文本)，共 63 个必修代码
全部排入。

- Y1：普通生物学 I/II(1901/1902)+对应实验室(1903/1904)、普通化学(1011/1012)+实验室
  (1051/1052)。HKDSE 生物达 3 级或以上者可依官方 Note 免修 LIFS1901/1903。
- Y2：现代生化研究方法(2010)、生化 I(2210)、有机化学(2111)或分析化学(2311)二选一
  (需与对应实验室 2155/2355 配对)、细胞生物学(2040)、生化 II(2220)、细胞生物学实验室(2240)。
- Y3：生化实验室(2720)、分子细胞生物学 I/II(3010/3020)、遗传学(3140)、生化实验技术(2820)。
- Y4：毕业论文路径三选一 —— 单学期 Capstone(4961)，或两学期 Project Research
  (4971→4981)，或 IRE 学生的(SCIE4500→4981)。IRE Track 的 3 门必修课
  (LIFS3070/LIFS3110/SCIE3500) 作为可选 Track 整体列入 Y4_FALL 并注明仅 IRE 学生需修。
- School Requirements（组合选修，与 Major Prerequisite/Required 高度重叠）整组列入
  Y1_SPRING 并注明"组内选修"性质。
- Elective(s)：12-24 学分（依毕业论文路径不同而变化），未逐一列入学期，
  见 `elective_requirement`。

---

## 自查结果（实测，非预期值）

```
$ python3 -m json.tool seed/raw/hkust_programs/term_plans.json   # -> 有效 JSON
COMP required_total=33 used=32 missing=['MATH 2540']   # 唯一缺口=已记录的抓取伪影，故意排除
CENG required_total=36 used=36 missing=[]
MATH required_total=89 used=89 missing=[]
MECH required_total=39 used=39 missing=[]
BCB  required_total=63 used=63 missing=[]
```

5 个专业 × 8 个学期（Y1_FALL...Y4_SPRING）字段齐全；所有排入学期的课程码均从
`programs.json` 对应专业的 `requirement_groups[*].course_codes` 中取值，未发明任何课程码。
