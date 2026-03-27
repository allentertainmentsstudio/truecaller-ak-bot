FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc libffi-dev

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
