"""Trusted bounded local decoder subprocess; stdin pixels, stdout JSON, never follows URLs."""
import json
import sys
import cv2
import numpy as np
cv2.setNumThreads(1)
data = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
if len(data) > 10 * 1024 * 1024:
    raise ValueError('Decode input too large')
image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
if image is None or image.shape[0]*image.shape[1] > 16_000_000:
    raise ValueError('Invalid decoder input')
values = []
qr = cv2.QRCodeDetector()
try:
    ok, decoded, _, _ = qr.detectAndDecodeMulti(image)
    if ok: values.extend(x for x in decoded if x)
except cv2.error:
    pass
if not values:
    try:
        value, _, _ = qr.detectAndDecode(image)
        if value: values.append(value)
    except cv2.error:
        pass
barcode_available = hasattr(cv2, 'barcode_BarcodeDetector')
if barcode_available:
    try:
        ok, decoded, _, _ = cv2.barcode_BarcodeDetector().detectAndDecodeWithType(image)
        if ok: values.extend(x for x in decoded if x)
    except cv2.error:
        pass
print(json.dumps({'values': sorted(set(x for x in values if len(x) <= 4000))[:32],
                  'decoder': 'opencv-'+cv2.__version__, 'barcode_available': barcode_available}))
