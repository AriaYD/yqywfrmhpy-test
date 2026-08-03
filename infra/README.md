# infra —— GCP 资源（WP0）

```bash
bash infra/bootstrap.sh            # dry-run：只打印将要做什么
bash infra/bootstrap.sh --apply    # 真的创建（幂等，可重复跑）
bash infra/verify.sh               # 只读实测：资源是否真的存在、权限是否真的对
bash infra/cost.sh                 # 每日成本检查
bash infra/moodle.sh status        # Moodle 沙箱状态
```

## 三条设计决定

**默认 dry-run。** 所有会改动资源的脚本，不加 `--apply` 就只打印。
手滑跑一次不该产生账单。

**bootstrap 与 verify 分开。** `bootstrap.sh` 跑完不报错，只说明命令返回了 0；
它不说明资源真的建成、权限真的生效。`verify.sh` 去**取实测值**（Plan §10 H3）。
最有价值的是里面的**否定式检查**：A4 的服务账户**不该**有学生数据权限。
肯定式检查只能发现"忘了建"，否定式检查才能发现"多给了"。

**Moodle VM 单独一个脚本。** 它是唯一有实质月成本的资源（约 HK$195/月）。
放进 bootstrap 就会变成"跑一下初始化"顺手开出一台机器。
赠金 2026-09-27 过期，别让闲置 VM 吃掉本该给模型调用的额度。

## 资源清单

| 资源 | 名称 | 说明 |
|---|---|---|
| Firestore | `(default)`，Native 模式 | Canonical Profile + append-only Event Store |
| Cloud Storage | `campuspath-evidence-<project>` | Private Vault，按 `student_id` 前缀隔离；已阻断公开访问 |
| Artifact Registry | `campuspath` | 容器镜像 |
| 服务账户 | `campuspath-student-runtime` | A0/A1/A2/A3/A5：模型 + Firestore + Vault + trace |
| 服务账户 | `campuspath-opportunity-runtime` | **A4：只有模型与 trace，没有任何学生数据权限** |
| 服务账户 | `campuspath-moodle-reader` | 只读 Secret，不碰 Firestore |
| Secret Manager | 见 `config.sh` 的 `REQUIRED_SECRETS` | 只建空密钥，值由人工注入 |
| GCE | `campuspath-moodle` | Moodle 沙箱，按需开关 + 夜间停机 |

## 两个 Runtime 为什么用两个服务账户

Spec §8.1 把 Student Path Runtime 与 Opportunity Operations Runtime 分开，
不是为了扩缩容，是**安全边界**：A4 处理系统里唯一的不可信输入
（外部抓取内容与 Publisher 投稿）。

共用一个服务账户，这条边界就只剩下代码里的自觉。
所以 `bootstrap.sh` 给 A4 的角色里**没有** `roles/datastore.user`，
`verify.sh` 会主动去查它有没有被人后来加上。
改这里之前，先去看 D2 的安全契约测试。

## 密钥

`bootstrap.sh` 只创建**空**的 Secret 容器，不放值。注入方式：

```bash
printf '%s' "$VALUE" | gcloud secrets versions add campuspath-moodle-ws-token --data-file=-
```

值不进仓库、不进文档、不进提交信息（Plan §9）。
`verify.sh` 会报告哪些密钥"存在但没有值"——那些功能会在运行时失败，
早知道比 Demo 现场知道好。

## 已知的不舒服之处

- **gcloud 调用慢。** dry-run 也要逐个 `describe` 才能判断资源是否存在，
  在本机上整轮要几分钟。没有绕过办法，除非放弃幂等性。
- **`cost.sh` 不给精确金额。** 准确用量要把账单导出到 BigQuery。
  与其给一个不准的数字，不如准确回答"现在有什么在按时间计费"。
- **Vertex 区域是实测而非断言。** `config.sh` 里的 `VERTEX_LOCATION` 只是默认值，
  由 `verify.sh` 在运行时问一次 API。区域支持哪些模型会变，写死在文档里迟早过期。
