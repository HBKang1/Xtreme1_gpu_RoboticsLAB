# YOLO26 image detection service for Xtreme1.
# Base image already carries torch + CUDA + ultralytics; only the http layer is missing.
FROM ultralytics/ultralytics:latest

RUN pip install --no-cache-dir flask

WORKDIR /app
# Also bind-mounted in docker-compose so app.py edits apply on restart without a rebuild.
COPY app.py /app/app.py

EXPOSE 5000
CMD ["python", "app.py"]
