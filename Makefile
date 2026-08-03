# CampusPath —— 常用命令
#
# 反馈环要快（Plan §10.5）：`make smoke` 必须 < 10 秒，这是最常用的命令。
# 重的全量验证只在 WP 收尾和交付前跑。

PY := .venv/bin/python
CONTRACTS := contracts
SEED := seed

# 确定性服务平面（**零 LLM**，受 B11/B12 四层扫描约束）。
DETERMINISTIC := rules capacity wellbeing state action aggregation monitor publishing \
                 connector mock-campus packs

# 编排层：日后会调用 Agent（WP6），因此**不**在零 LLM 名单里——
# 但它调用的每个确定性服务仍各自受约束。混进上面那行会让 B11 的口径变空。
ORCHESTRATION := api

SERVICES := $(DETERMINISTIC) $(ORCHESTRATION)

# 评测 harness 独立成包：它 import 全部服务，**不能**被任何服务 import。

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "CampusPath"
	@echo ""
	@echo "  make setup            创建 .venv 并安装全部包"
	@echo "  make preflight        开工自检（计费、密钥、基线文档）"
	@echo "  make smoke            最小验证，目标 < 10 秒"
	@echo "  make test             契约 + Seed + 全部确定性服务"
	@echo ""
	@echo "  make contracts        重新导出 JSON Schema + OpenAPI"
	@echo "  make contracts-check  断言磁盘产物与代码一致（CI 用）"
	@echo "  make types            从 OpenAPI 生成前端 TypeScript 类型"
	@echo ""
	@echo "  make seed             生成 full + tiny 数据集"
	@echo "  make seed-reset       删除旧产物后重新生成（可复现性演示）"
	@echo "  make seed-check       跨表一致性校验"
	@echo "  make seed-selftest    用已知矛盾验证一致性检查器"
	@echo ""
	@echo "  make mock-campus      本地起 Mock Campus REST（:8080）"
	@echo "  make llm-free         全部确定性服务的零 LLM 扫描（B11/B12）"
	@echo "  make harness-selftest 验证 make 在测试失败时真的会非零退出"
	@echo "  make check            上述全部 + llm-free + harness-selftest"
	@echo "  make eval             D6 验收：13 BLOCKER + 12 TARGET，机器判定"
	@echo ""
	@echo "  确定性服务（零 LLM）：$(DETERMINISTIC)"
	@echo "  编排层：$(ORCHESTRATION) + agents（A0–A5）"

.PHONY: setup
setup:
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -e "$(CONTRACTS)[dev]" -e "$(SEED)[dev]" \
		$(foreach s,$(SERVICES),-e "services/$(s)[dev]") -e "eval[dev]"

# D6 的验收合同：一条命令产出机器判定的 PASS / FAIL。
# 退出码分级——任何 BLOCKER 未通过就非零，仅 TARGET 未达标退出 0 但报告标红。
# **不加 `|| true`**：这条命令的价值全在它会失败。
.PHONY: eval
eval:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	PYTHONPATH=eval $(PY) -m campuspath_eval

.PHONY: preflight
preflight:
	bash scripts/preflight.sh

# smoke 只跑最能反映"地基有没有塌"的几组：validation_id 绑定、数据域边界、
# Seed 自洽、先修判定、Wellbeing 前置条件。
.PHONY: smoke
smoke:
	@cd $(CONTRACTS) && PYTHONPATH=.:tests ../$(PY) -m pytest tests -o addopts= -q -x \
		-k "validation or boundary or wellbeing"
	@cd $(SEED) && PYTHONPATH=.:tests ../$(PY) -m pytest tests -o addopts= -q -x \
		-k "tiny or consistent"
	@cd services/rules && PYTHONPATH=.:tests ../../$(PY) -m pytest tests -o addopts= -q -x \
		-k "prerequisite or wellbeing or protected or capacity"
	@cd services/wellbeing && PYTHONPATH=.:tests ../../$(PY) -m pytest tests -o addopts= -q -x \
		-k "disclaimer or consent or reminder"

.PHONY: test
test: test-contracts test-seed test-services test-agents test-mcp

# Agent 层不在 services/ 下：它是**调用者**，不是被调用的服务。
.PHONY: test-mcp
test-mcp:
	@cd mcp && PYTHONPATH=.:tests ../$(PY) -m pytest tests -o addopts= -q

.PHONY: test-agents
test-agents:
	@cd agents && PYTHONPATH=.:tests ../$(PY) -m pytest tests -o addopts= -q

.PHONY: test-contracts
test-contracts:
	@cd $(CONTRACTS) && PYTHONPATH=.:tests ../$(PY) -m pytest tests -o addopts= -q

.PHONY: test-seed
test-seed:
	@cd $(SEED) && PYTHONPATH=.:tests ../$(PY) -m pytest tests -o addopts= -q

# 逐个服务跑，**并把失败传出去**。
# 之前这里是 `... | tail -1`：管道吃掉了 pytest 的退出码，for 循环又不累积状态，
# 于是注入一个必失败的测试，`make check` 照样返回 0——所有"全绿"都失去验证力。
# `scripts/check_make_fails.sh` 是这条的防回归探针。
.PHONY: test-services
test-services:
	@rc=0; for s in $(SERVICES); do \
		printf '%-14s ' "$$s"; \
		if out=$$(cd services/$$s && PYTHONPATH=.:tests ../../$(PY) -m pytest tests -o addopts= -q 2>&1); then \
			printf '%s\n' "$$out" | tail -1; \
		else \
			rc=1; printf '\033[31mFAILED\033[0m\n'; printf '%s\n' "$$out" | tail -25; \
		fi; \
	done; exit $$rc

# B11/B12：三层扫描（运行时依赖 / 声明依赖树 / 源码 import），逐服务跑。
.PHONY: llm-free
llm-free:
	@rc=0; for s in $(DETERMINISTIC); do \
		printf '%-14s ' "$$s"; \
		if out=$$(cd services/$$s && PYTHONPATH=.:tests ../../$(PY) -m pytest tests/test_llm_free*.py -o addopts= -q 2>&1); then \
			printf '%s\n' "$$out" | tail -1; \
		else \
			rc=1; printf '\033[31mFAILED\033[0m\n'; printf '%s\n' "$$out" | tail -25; \
		fi; \
	done; exit $$rc

.PHONY: contracts
contracts:
	@cd $(CONTRACTS) && ../$(PY) scripts/export_schemas.py

.PHONY: contracts-check
contracts-check:
	@cd $(CONTRACTS) && ../$(PY) scripts/export_schemas.py --check

# 前端类型从**同一份** OpenAPI 生成（Plan WP1 验收条款）。
# 产物入库，这样前端不必先跑生成器就能开工，契约变更也能在 diff 里看到。
# 本地起 Mock Campus（WP4）。Cloud Run 部署脚本在 infra/，按需再写。
# 学生端 Web App（WP7）连的就是它。
# **必须 source .env**：模型后端靠 GOOGLE_GENAI_USE_VERTEXAI 等环境变量选择，
# 少了它 Deps 会退回 model=None，依赖模型的端点全部 503——
# 而那看起来像"功能没做"，其实是"忘了带环境"。
.PHONY: api
api:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	$(PY) -m uvicorn campuspath_api.app:app --reload --port 8000 \
		--app-dir services/api

.PHONY: web
web:
	@cd apps/web && bun run dev --port 3100

.PHONY: mock-campus
mock-campus:
	@$(PY) -m uvicorn campuspath_mock_campus.app:app --reload --port 8080 \
		--app-dir services/mock-campus

.PHONY: types
types:
	@cd $(CONTRACTS) && bunx --bun openapi-typescript@7 openapi/campuspath.json \
		-o generated/campuspath-api.d.ts

.PHONY: seed
seed:
	@PYTHONPATH=$(SEED) $(PY) -m campuspath_seed.cli --profile full build
	@PYTHONPATH=$(SEED) $(PY) -m campuspath_seed.cli --profile tiny build

.PHONY: seed-reset
seed-reset:
	@PYTHONPATH=$(SEED) $(PY) -m campuspath_seed.cli --profile full build --reset
	@PYTHONPATH=$(SEED) $(PY) -m campuspath_seed.cli --profile tiny build --reset
	@PYTHONPATH=$(SEED) $(PY) -m campuspath_seed.cli --profile full reproduce

.PHONY: seed-check
seed-check:
	@PYTHONPATH=$(SEED) $(PY) -m campuspath_seed.cli --profile full check
	@PYTHONPATH=$(SEED) $(PY) -m campuspath_seed.cli --profile tiny check

.PHONY: seed-selftest
seed-selftest:
	@PYTHONPATH=$(SEED) $(PY) -m campuspath_seed.cli --profile full selftest

# 验证链本身也要被验证：make 的退出码曾经恒为 0（见 test-services 的注释）。
.PHONY: harness-selftest
harness-selftest:
	@bash scripts/check_make_fails.sh

.PHONY: check
check: preflight contracts-check seed-check test llm-free harness-selftest
	@echo "全部通过"

.PHONY: sources-refresh
sources-refresh:            # 每日源巡检（本地；云端形态见 infra/sources_job.sh）
	$(PY) jobs/sources_refresh.py
