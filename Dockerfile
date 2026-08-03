# CampusPath API → Cloud Run（演示部署）。
#
# 不 pip install 本仓包——各包以源码目录进 PYTHONPATH（与 Makefile 同一口径），
# 避免"装进 site-packages 后数据文件相对路径全断"这一类坑。
# 模型调用走 Vertex（Cloud Run 服务账号 ADC，吃赠金项目）；
# ⚠️ 不注入 GOOGLE_TEST_ACCOUNT_EMAIL——公网实例的联系人 fixture
# 回落到 example.invalid 哑地址，测试邮箱不出本机。
FROM python:3.12-slim

WORKDIR /app
COPY contracts contracts
COPY seed seed
COPY services services
COPY agents agents
COPY jobs jobs

RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn>=0.30" "pydantic>=2.7" \
    "google-genai>=1.0" "google-auth>=2.30" "pypdf>=5.0"

ENV PYTHONPATH=/app/contracts:/app/seed:/app/agents:/app/services/api:/app/services/rules:/app/services/capacity:/app/services/wellbeing:/app/services/state:/app/services/action:/app/services/aggregation:/app/services/publishing:/app/services/monitor:/app/services/connector:/app/services/packs:/app/services/mock-campus
ENV GOOGLE_GENAI_USE_VERTEXAI=TRUE

CMD exec python -m uvicorn campuspath_api.app:app --host 0.0.0.0 --port ${PORT:-8080}
