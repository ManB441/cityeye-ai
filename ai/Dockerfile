FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

COPY requirements.runtime.txt ./
RUN pip install --no-cache-dir --index-url "${PYTORCH_INDEX_URL}" \
      torch==2.13.0 torchvision==0.28.0
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
      --index-url https://pypi.org/simple \
      -r requirements.runtime.txt

COPY . ./

CMD ["python", "process_video.py", "--config", "config/live_camera.json.example", "--output-dir", "live_output"]
