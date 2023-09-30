FROM python:3.9-slim-buster

ENV IS_IN_DOCKER 1

WORKDIR /app

COPY docker/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
