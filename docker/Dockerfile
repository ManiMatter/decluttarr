#FROM python:3.9-slim-buster
# For debugging:
# sudo docker run --rm -it  --entrypoint sh  ghcr.io/manimatter/decluttarr:dev 

FROM python:3.10.13-slim

# Define a build-time argument for IMAGE_TAG
ARG IMAGE_TAG

# Set an environment variable using the build-time argument
ENV IMAGE_TAG=$IMAGE_TAG
ENV SHORT_COMMIT_ID=$SHORT_COMMIT_ID

LABEL org.opencontainers.image.source="https://github.com/ManiMatter/decluttarr"
                                                      
ENV IS_IN_DOCKER 1

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir -r docker/requirements.txt


CMD ["python", "main.py"]
