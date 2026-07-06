FROM python:3.11-slim AS builder

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system --no-cache fastapi "uvicorn[standard]" pydantic-settings \
    "redis[hiredis]" loguru python-multipart openai deepgram-sdk \
    PyMuPDF openpyxl python-docx rank-bm25

FROM python:3.11-slim AS runtime

RUN groupadd -r copilot && useradd -r -g copilot copilot
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

RUN chown -R copilot:copilot /app
USER copilot

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
