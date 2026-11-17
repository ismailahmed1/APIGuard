# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

# Every experiment uses this NexStock commit (v1, before the v2 multi-warehouse release).
ARG NEXSTOCK_COMMIT=616e053ebda66294f5d3532dae4b3d752acc6cb0
ADD https://github.com/heetdadhania/NexStock.git#${NEXSTOCK_COMMIT} /nexstock

WORKDIR /nexstock/backend
COPY constraints.txt /tmp/constraints.txt
RUN pip install --no-cache-dir -r requirements.txt -c /tmp/constraints.txt

# Optional seeded fault for evaluation; empty builds the original application.
ARG NEXSTOCK_FAULT=
COPY faults/ /tmp/faults/
RUN if [ -n "$NEXSTOCK_FAULT" ]; then \
      apt-get update && apt-get install --yes --no-install-recommends patch && \
      patch --directory=/nexstock --strip=1 --forward < "/tmp/faults/$NEXSTOCK_FAULT.patch"; \
    fi

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
