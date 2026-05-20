# Container para rodar o mock via Functions Framework (compatível com Cloud Functions Gen2 / Cloud Run)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FLOWLY_TEXT_ONLY=1 \
    FLOWLY_TTS_ENABLED=0 \
    FLOWLY_MOCK_DATA_PATH=/tmp/mock_data.json

WORKDIR /app

# Dependências
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY . .

EXPOSE 8080

# Functions Framework: carrega main.py e executa o handler HTTP
CMD ["functions-framework", "--target", "trigger_http", "--port", "8080"]
