import logging
import sys
from typing import Any, Optional
from src.config import settings


class LoggerSidecar:
    _instance: Optional[logging.Logger] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerSidecar, cls).__new__(cls)
            cls._logger = logging.getLogger("lowkey_ecom")
            cls._logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
            
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            cls._logger.addHandler(handler)
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

