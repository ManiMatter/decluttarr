import os
IS_IN_DOCKER = os.environ.get('IS_IN_DOCKER')
IMAGE_TAG = os.environ.get('IMAGE_TAG', 'Local')
SHORT_COMMIT_ID = os.environ.get('SHORT_COMMIT_ID', 'n/a')
