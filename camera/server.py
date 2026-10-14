"""Servicio mínimo que posee la webcam y sirve frames por HTTP.

GET /frame.jpg    -> frame reciente a resolución completa (para identificar)
GET /preview.jpg  -> frame reducido y más comprimido (para la vista previa)
GET /health       -> estado de la cámara

Un hilo hace grab() continuamente para que el buffer UVC no devuelva frames
antiguos, pero solo decodifica (retrieve) mientras alguien pide imágenes: en
reposo el coste de CPU en la Raspberry Pi es casi nulo.
"""

import json
import logging
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("camera")

DEVICE = os.environ.get("CAMERA_DEVICE_IN_CONTAINER", "/dev/video0")
WIDTH = int(os.environ.get("CAMERA_WIDTH", "1920"))
HEIGHT = int(os.environ.get("CAMERA_HEIGHT", "1080"))
FPS = int(os.environ.get("CAMERA_FPS", "15"))
FOURCC = os.environ.get("CAMERA_FOURCC", "MJPG")
# Controles v4l2 aplicados al abrir la cámara, en orden: "focus_automatic_continuous=0,focus_absolute=300"
CONTROLS = os.environ.get("CAMERA_CONTROLS", "")
PREVIEW_WIDTH = int(os.environ.get("CAMERA_PREVIEW_WIDTH", "960"))
PORT = int(os.environ.get("CAMERA_PORT", "8080"))

DECODE_INTERVAL = 0.2  # máx. ~5 frames decodificados por segundo
ACTIVE_WINDOW = 3.0  # segundos que se sigue decodificando tras la última petición
WAIT_TIMEOUT = 3.0


def apply_controls():
    for item in filter(None, (c.strip() for c in CONTROLS.split(","))):
        result = subprocess.run(
            ["v4l2-ctl", "-d", DEVICE, "-c", item], capture_output=True, text=True
        )
        if result.returncode == 0:
            log.info("Control aplicado: %s", item)
        else:
            log.warning("Control %s falló: %s", item, result.stderr.strip())


class Camera:
    def __init__(self):
        self._cond = threading.Condition()
        self._frame = None
        self._frame_at = 0.0  # time.monotonic() del frame
        self._last_request = 0.0
        self._preview = (0.0, None)  # (frame_at, jpeg) cacheado
        self.opened = False

    def _open(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*FOURCC))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FPS)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def run(self):
        while True:
            cap = self._open()
            if not cap.isOpened():
                log.warning("No se pudo abrir %s; reintento en 3 s", DEVICE)
                time.sleep(3)
                continue
            apply_controls()
            self.opened = True
            log.info(
                "Cámara abierta: %sx%s @ %s fps",
                int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                int(cap.get(cv2.CAP_PROP_FPS)),
            )
            last_decode = 0.0
            while cap.grab():
                now = time.monotonic()
                active = now - self._last_request < ACTIVE_WINDOW
                if not active or now - last_decode < DECODE_INTERVAL:
                    continue
                ok, frame = cap.retrieve()
                if not ok:
                    continue
                last_decode = now
                with self._cond:
                    self._frame, self._frame_at = frame, now
                    self._cond.notify_all()
            log.warning("Lectura fallida; reabriendo cámara")
            self.opened = False
            cap.release()
            time.sleep(1)

    def frame(self, max_age: float):
        """Frame decodificado con antigüedad <= max_age (espera si hace falta)."""
        self._last_request = time.monotonic()
        with self._cond:
            fresh = lambda: self._frame is not None and time.monotonic() - self._frame_at <= max_age  # noqa: E731
            self._cond.wait_for(fresh, timeout=WAIT_TIMEOUT)
            return self._frame, self._frame_at

    def full_jpeg(self) -> bytes | None:
        frame, _ = self.frame(max_age=0.5)
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return buf.tobytes() if ok else None

    def preview_jpeg(self) -> bytes | None:
        frame, frame_at = self.frame(max_age=1.0)
        if frame is None:
            return None
        cached_at, cached = self._preview
        if cached_at == frame_at:
            return cached
        h, w = frame.shape[:2]
        if w > PREVIEW_WIDTH:
            frame = cv2.resize(frame, (PREVIEW_WIDTH, int(h * PREVIEW_WIDTH / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return None
        self._preview = (frame_at, buf.tobytes())
        return self._preview[1]

    def status(self) -> dict:
        age = time.monotonic() - self._frame_at if self._frame_at else None
        return {"opened": self.opened, "device": DEVICE, "frame_age_s": age}


camera = Camera()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_jpeg(self, data: bytes | None):
        if data is None:
            self._send(503, b'{"detail": "sin frames de la camara"}', "application/json")
        else:
            self._send(200, data, "image/jpeg")

    def do_GET(self):
        if self.path.startswith("/frame.jpg"):
            self._send_jpeg(camera.full_jpeg())
        elif self.path.startswith("/preview.jpg"):
            self._send_jpeg(camera.preview_jpeg())
        elif self.path.startswith("/health"):
            status = camera.status()
            self._send(200 if status["opened"] else 503, json.dumps(status).encode(), "application/json")
        else:
            self._send(404, b'{"detail": "not found"}', "application/json")

    def log_message(self, *args):  # silencia el log por petición del preview
        pass


if __name__ == "__main__":
    threading.Thread(target=camera.run, daemon=True).start()
    log.info("Escuchando en :%s", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
