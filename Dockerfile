# Runs the toolkit the same way on any machine with Docker — a VPS, a
# laptop (Windows/macOS/Linux), or most "deploy from a Dockerfile" hosting
# platforms (Railway, Render, Fly.io, etc).
FROM python:3.11-slim

# build-essential is only needed to compile tgcrypto on platforms without a
# prebuilt wheel (e.g. some ARM boards / less common architectures).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the Telegram bot. Override at `docker run`/compose time to
# run generate_session.py or validate_session.py instead, e.g.:
#   docker run --rm -it --env-file .env <image> python3 generate_session.py
CMD ["python3", "telegram_session_bot.py"]
