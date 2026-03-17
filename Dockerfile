FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    REVIEW_CLAUDE_BIN=claude

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8790

CMD ["python3", "review_ui/server.py", "--host", "0.0.0.0", "--port", "8790"]
