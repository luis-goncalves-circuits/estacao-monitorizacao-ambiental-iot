# Construir com contexto na raiz do projeto (ver docker-compose.yml: context: .., dockerfile: api/Dockerfile)
FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/api.py .
COPY web ./web
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
