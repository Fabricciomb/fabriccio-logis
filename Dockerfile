# Usa uma imagem leve do Python
FROM python:3.11-slim

# Instala dependências do sistema necessárias para algumas bibliotecas
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Define o diretório de trabalho
WORKDIR /app

# Copia os requisitos e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código
COPY . .

# Cria a pasta de dados para o banco SQLite e dá permissão
RUN mkdir -p /app/data && chmod 777 /app/data

# Expõe a porta que o Flask usa
EXPOSE 5000

# Comando para rodar com Gunicorn (melhor que o app.run padrão)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
