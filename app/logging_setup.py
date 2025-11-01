import logging
import json
import time
from flask import has_request_context, request

class JsonRequestFormatter(logging.Formatter):
    def format(self, record):
        # Si el log proviene del health check, se ignora
        if has_request_context() and request.path == "/healthz":
            return ""

        data = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        if has_request_context():
            data.update({
                "method": request.method,
                "path": request.path,
                "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr),
                "request_id": request.headers.get("X-Request-ID"),
            })

        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(data, ensure_ascii=False)

def setup_logging(app=None):
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # limpia handlers duplicados en reload
    for h in list(root.handlers):
        root.removeHandler(h)

    h = logging.StreamHandler()
    h.setFormatter(JsonRequestFormatter())
    root.addHandler(h)

    if app:
        app.logger.handlers = [h]
        app.logger.setLevel(logging.INFO)
