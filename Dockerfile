FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py index.html ./
EXPOSE 80
CMD ["gunicorn", "server:app", \
     "--bind", "0.0.0.0:80", \
     "--workers", "2", \
     "--timeout", "120"]
