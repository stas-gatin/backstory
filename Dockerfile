FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt
COPY backstory backstory
COPY web web
COPY examples examples
COPY replay replay
COPY eval/track_record.json eval/track_record.json
EXPOSE 8000
# a host such as Render gives the port in $PORT
CMD ["sh", "-c", "exec uvicorn backstory.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
