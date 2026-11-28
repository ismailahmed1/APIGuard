# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

# Every experiment uses this commit of the FastAPI Banking System.
ARG BANKING_COMMIT=6e8ed525c5bcc70e06820cefc661ab772da30317
ADD https://github.com/Dhruv-Cmds/fastapi-banking-system.git#${BANKING_COMMIT} /banking

WORKDIR /banking/backend
# requirements.txt pins every version.
RUN pip install --no-cache-dir -r requirements.txt

# Log each request and login as JSON for the security monitor (FR-11), and turn off the rate limits.
COPY --from=shared apiguard_logging.py /banking/backend/apiguard_logging.py
COPY apiguard_app.py /banking/backend/apiguard_app.py

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "--factory", "apiguard_app:create_app", "--host", "0.0.0.0", "--port", "8000"]
