FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
# CPU-only PyTorch (small). For NVIDIA GPU use the default PyPI wheels instead and run with --gpus all.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt
COPY . .
ENV SC_DATA_DIR=/data SC_HOST=0.0.0.0 SC_PORT=8000
VOLUME ["/data", "/app/models"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["python", "run.py"]
