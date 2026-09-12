FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY macs ./macs
RUN pip install --no-cache-dir .
COPY seed.py record.py ./
ENV PORT=8000
CMD ["sh", "-c", "uvicorn macs.app:app --host 0.0.0.0 --port ${PORT}"]
