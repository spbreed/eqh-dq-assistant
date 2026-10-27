# One image for the assistant service and the pipeline jobs (profiler / daily_sync / enrich / eval).
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY config ./config
COPY jobs ./jobs
COPY datagen/__init__.py datagen/payers.yaml datagen/seeded_defects.yaml ./datagen/
COPY datagen/domain ./datagen/domain
COPY datagen/glue_dq.py ./datagen/
COPY assistant ./assistant
COPY eval ./eval
RUN useradd -u 10001 app && chown -R app /app
USER app
EXPOSE 8080
CMD ["uvicorn", "assistant.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
