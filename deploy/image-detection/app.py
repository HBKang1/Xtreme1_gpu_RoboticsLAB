"""YOLO 2D image detection service for Xtreme1.

Speaks the contract the Java backend's IMAGE_DETECTION handler expects
(ImageDetectionReqDTO / ImageDetectionRespDTO):

  POST /image/recognition
  <-  {"datas": [{"id": 123, "url": "http://<host>/minio/xtreme1/....jpg"}]}
  ->  {"code": "OK", "message": "", "data": [
         {"id": 123, "code": "OK", "message": "", "objects": [
            {"label": "vehicle", "confidence": 0.93,
             "leftTopX": 100, "leftTopY": 50,
             "rightBottomX": 300, "rightBottomY": 220}]}]}

`label` must match `model_class.code` in the DB exactly (case sensitive) or the
annotation lands without a class name -- see ModelUseCase.getModelClassMapByModelId.
Labels come straight from the checkpoint's own names map, so register the codes
the weights were trained with (here: vehicle, pedestrian).
"""

import io
import logging
import os
import re
import threading

import requests
from flask import Flask, jsonify, request
from PIL import Image
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

WEIGHTS = os.environ.get('WEIGHTS', '/app/weights.pt')
IMGSZ = int(os.environ.get('IMGSZ', 640))
CONF = float(os.environ.get('CONF', 0.25))
IOU = float(os.environ.get('IOU', 0.7))
MAX_DET = int(os.environ.get('MAX_DET', 300))
DEVICE = os.environ.get('DEVICE', '0')
PORT = int(os.environ.get('PORT', 5000))

# The backend hands out gateway-facing MinIO urls (http://<host>/minio/...), which
# only resolve from outside the compose network. Rewrite back to the internal
# endpoint the presigned url was actually signed against -- same trick as
# deploy/point-cloud-detection/app.py:normalize_pcd_url.
_MINIO_PREFIX_RE = re.compile(r'^https?://[^/]+/minio(?=/)')

app = Flask(__name__)
model = None
# One RTX 3080 shared with the point cloud service: serialise inference so two
# concurrent model runs can't blow the remaining ~5GB of VRAM.
lock = threading.Lock()


def normalize_url(url: str) -> str:
    return _MINIO_PREFIX_RE.sub('http://minio:9000', url)


def load_model():
    global model
    logging.info(f'loading {WEIGHTS} (imgsz={IMGSZ} conf={CONF} device={DEVICE})')
    model = YOLO(WEIGHTS)
    logging.info(f'class names: {model.names}')
    # Warm up so the first real request isn't paying for cuda init + autotune.
    model.predict(Image.new('RGB', (IMGSZ, IMGSZ)), imgsz=IMGSZ,
                  device=DEVICE, verbose=False)
    logging.info('model ready')


def item_error(data_id, code, message):
    return {'id': data_id, 'code': code, 'message': message, 'objects': []}


def process_data(data):
    if not isinstance(data, dict):
        return item_error(None, 'InvalidArgument', 'data must be an object')

    data_id = data.get('id')
    url = data.get('url')
    if data_id is None:
        return item_error(None, 'InvalidArgument', 'missing "id"')
    if not url:
        return item_error(data_id, 'InvalidArgument', 'missing "url"')

    try:
        resp = requests.get(normalize_url(url), allow_redirects=True, timeout=60)
        resp.raise_for_status()
        image = Image.open(io.BytesIO(resp.content)).convert('RGB')
    except Exception as e:
        logging.exception(f'download failed, id={data_id}')
        return item_error(data_id, 'SystemError', f'download failed: {e}')

    try:
        with lock:
            result = model.predict(image, imgsz=IMGSZ, conf=CONF, iou=IOU,
                                   max_det=MAX_DET, device=DEVICE,
                                   verbose=False)[0]
    except Exception as e:
        logging.exception(f'inference failed, id={data_id}')
        return item_error(data_id, 'SystemError', f'inference failed: {e}')

    objects = []
    for box in result.boxes:
        x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
        objects.append({
            'label': result.names[int(box.cls)],
            'confidence': round(float(box.conf), 4),
            'leftTopX': round(x1, 2),
            'leftTopY': round(y1, 2),
            'rightBottomX': round(x2, 2),
            'rightBottomY': round(y2, 2),
        })

    logging.info(f'id={data_id} objects={len(objects)}')
    return {'id': data_id, 'code': 'OK', 'message': '', 'objects': objects}


@app.post('/image/recognition')
def recognition():
    body = request.get_json(silent=True) or {}
    datas = body.get('datas')
    if not isinstance(datas, list) or not datas:
        return jsonify({'code': 'InvalidArgument',
                        'message': '"datas" must be a non-empty list',
                        'data': []})
    return jsonify({'code': 'OK', 'message': '',
                    'data': [process_data(d) for d in datas]})


@app.get('/health')
def health():
    return jsonify({'code': 'OK', 'message': '',
                    'data': {'weights': WEIGHTS, 'names': model.names}})


if __name__ == '__main__':
    load_model()
    app.run(host='0.0.0.0', port=PORT, threaded=True)
