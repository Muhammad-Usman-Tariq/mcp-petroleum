FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 8001

CMD ["sh", "-c", "uvicorn mcpserver.server:app --host 0.0.0.0 --port 8000 & uvicorn admin.main:app --host 0.0.0.0 --port 8001"]