# 50 块的机器只需要 100MB 内存，镜像越小越好
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 MONEYBOT_DB=/app/data/state.db PORT=8080

COPY core ./core
COPY main.py serve.py config.json ./
COPY data/fixtures ./data/fixtures

RUN mkdir -p /app/data /app/site && \
    useradd -m -u 10001 moneybot && chown -R moneybot /app
USER moneybot

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python3 -c \
  "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/')" || exit 1

# 首次启动先产出一期，再起服务
CMD ["sh", "-c", "python3 main.py run || true; python3 serve.py --port 8080 --root site"]
