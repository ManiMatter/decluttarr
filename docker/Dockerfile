#FROM python:3.9-slim-buster
FROM python:3.10.13-slim
LABEL org.opencontainers.image.source="https://github.com/ManiMatter/decluttarr"
                                                      
ENV IS_IN_DOCKER 1

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir -r docker/requirements.txt


CMD ["python", "main.py"]
