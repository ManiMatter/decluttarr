#FROM python:3.9-slim-buster
# For debugging:
    # First build:  
    # sudo docker build --no-cache --progress=plain -f ./docker/Dockerfile -t decluttarr .

    # Entering image (and printing env variables):
    # sudo docker run --rm -it -w /app --entrypoint sh decluttarr -c "printenv; exec sh"

    # Then run from host (using docker-compose and as image: decluttarr:latest)  
    # sudo docker run --rm -v "/config:/app/config" --name decluttarr decluttarr

    # Entering running container:
    # sudo docker exec -it -w /app decluttarr sh -c "printenv; exec sh"
    # Alternatively: Inspect env vars via portainer



FROM python:3.10.13-slim

# Define a build-time argument for IMAGE_TAG
ARG IMAGE_TAG
ARG SHORT_COMMIT_ID

# Set an environment variable using the build-time argument
ENV IMAGE_TAG=$IMAGE_TAG
ENV SHORT_COMMIT_ID=$SHORT_COMMIT_ID

LABEL org.opencontainers.image.source="https://github.com/ManiMatter/decluttarr"
                                                      
ENV IN_DOCKER=true

WORKDIR /app
# Copy files
COPY ./docker/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py main.py
COPY src src


# Install health check
RUN apt-get update && apt-get install -y --no-install-recommends procps && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD pgrep -f main.py || exit 1

EXPOSE 9999

CMD ["python", "main.py"]

# For debugging:
# CMD ["sh", "-c", "while true; do sleep 1000; done"]
