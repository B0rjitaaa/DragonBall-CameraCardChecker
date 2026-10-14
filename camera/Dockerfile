FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# v4l-utils: permite ajustar foco/exposición con `docker compose exec camera v4l2-ctl ...`
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 v4l-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install numpy==2.1.3 opencv-python-headless==4.10.0.84

WORKDIR /app
COPY server.py .

EXPOSE 8080
CMD ["python", "server.py"]
