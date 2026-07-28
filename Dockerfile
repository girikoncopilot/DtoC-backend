FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY bundled-framework ./bundled-framework
COPY framework ./framework
COPY .env.example ./
COPY README.md ./

EXPOSE 8787

CMD ["sh", "-c", "uvicorn app.main:app --host ${AEF_HOST:-0.0.0.0} --port ${AEF_PORT:-8787}"]
