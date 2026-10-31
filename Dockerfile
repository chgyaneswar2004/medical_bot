FROM python:3.10-slim-bookworm

WORKDIR /app

COPY requirements.txt .
COPY setup.py .
COPY src ./src
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates
COPY static ./static

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120", "app:app"]
