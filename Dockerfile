# ============================================================
# VideoDown — Single-File Flask Video Downloader
# ============================================================
# Local:
#   docker build -t videodown .
#   docker run -p 5000:5000 -v vd-data:/app/data videodown
#
# Render:  render.yaml (Blueprint) builds this Dockerfile as-is.
#
# NOTE: yt-dlp updates often (site changes). Rebuild the image
# periodically:  docker build --no-cache -t videodown .
# ============================================================

FROM python:3.12-slim

# ffmpeg → MP3 conversion + HD (DASH) stream merging
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY videodown.py .

# /app/data holds videodown_cookies.txt + videodown_config.json —
# mount a volume/disk here to keep login cookies across restarts.
RUN mkdir -p /app/data
ENV VD_DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request,os,sys; p=int(os.environ.get('PORT','5000')); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%d/' % p).status==200 else 1)"

# 1 worker + threads: download jobs live in process memory, so all
# requests must land on the same process. Long timeout: slow sites.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 8 --timeout 300 --graceful-timeout 30 videodown:app"]
