"""
Structured logging. One JSON object per line so CloudWatch Insights can
query it without regex.
"""
import json
import sys
import time


class Logger:
    def _emit(self, level, message, fields):
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": level,
            "message": message,
        }
        entry.update({k: v for k, v in fields.items() if v is not None})
        print(json.dumps(entry, default=str), file=sys.stderr, flush=True)

    def info(self, message, **fields):
        self._emit("info", message, fields)

    def warn(self, message, **fields):
        self._emit("warn", message, fields)

    def error(self, message, exc=None, **fields):
        if exc is not None:
            fields["error"] = f"{type(exc).__name__}: {exc}"
        self._emit("error", message, fields)


logger = Logger()
