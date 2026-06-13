import logging
import json
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "app.log"

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage()
        }
        
        # Attach standard observability fields if they exist
        if hasattr(record, "request_id"):
            log_obj["request_id"] = record.request_id
        if hasattr(record, "endpoint"):
            log_obj["endpoint"] = record.endpoint
        if hasattr(record, "method"):
            log_obj["method"] = record.method
        if hasattr(record, "response_time_ms"):
            log_obj["response_time_ms"] = record.response_time_ms
        if hasattr(record, "status_code"):
            log_obj["status_code"] = record.status_code
        if hasattr(record, "user_id"):
            log_obj["user_id"] = record.user_id
            
        return json.dumps(log_obj)

def get_logger():
    logger = logging.getLogger("trident_app_logger")
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    numeric_level = getattr(logging, log_level, logging.INFO)
    logger.setLevel(numeric_level)
    
    # Avoid duplicate handlers in dev mode
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5 # 10MB limit
        )
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        
    return logger

app_logger = get_logger()
