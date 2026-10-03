FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x start.sh
ENV PYTHONUNBUFFERED=1
ENV API_URL=http://127.0.0.1:8000/api/v1/query
CMD ["./start.sh"]
