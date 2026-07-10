import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Optional
from src.config import settings


class LoggerSidecar:
    _instance: Optional[logging.Logger] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerSidecar, cls).__new__(cls)
            cls._logger = logging.getLogger("lowkey_ecom")
            cls._logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            cls._logger.addHandler(stream_handler)

            # On-disk, rotated log file — `docker logs` output isn't
            # persistent across container recreation, so anything that needs
            # to survive a redeploy or be pulled off the server (e.g. for
            # webhook debugging) has to also land on a mounted volume.
            try:
                os.makedirs(settings.log_dir, exist_ok=True)
                file_handler = RotatingFileHandler(
                    os.path.join(settings.log_dir, settings.log_file_name),
                    maxBytes=20 * 1024 * 1024,
                    backupCount=10,
                )
                file_handler.setFormatter(formatter)
                cls._logger.addHandler(file_handler)

                # uvicorn's request access log ("GET /path HTTP/1.1" 200) and
                # its own error log are on SEPARATE loggers from ours
                # ("uvicorn.access" / "uvicorn.error") — without this they'd
                # only ever exist in `docker logs`, which is lost on every
                # container restart/recreate, unlike this mounted volume.
                for uvicorn_logger_name in ("uvicorn.access", "uvicorn.error"):
                    uvicorn_logger = logging.getLogger(uvicorn_logger_name)
                    uvicorn_logger.addHandler(file_handler)
            except OSError as e:
                cls._logger.warning(f"Could not set up file logging at {settings.log_dir}: {e}")
        return cls._instance
    
    def info(self, message: str, *args: Any, **kwargs: Any):
        self._logger.info(message, *args, **kwargs)
    
    def error(self, message: str, *args: Any, **kwargs: Any):
        self._logger.error(message, *args, **kwargs)
    
    def warning(self, message: str, *args: Any, **kwargs: Any):
        self._logger.warning(message, *args, **kwargs)
    
    def debug(self, message: str, *args: Any, **kwargs: Any):
        self._logger.debug(message, *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any):
        self._logger.error(message, *args, **kwargs)
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


logger = LoggerSidecar.get_instance()

