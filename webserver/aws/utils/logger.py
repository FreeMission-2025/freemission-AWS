import logging

logger = logging.getLogger("__")
logger.setLevel(logging.INFO)

# Prevent duplicate handlers
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt='%(name)s:%(filename)s:%(lineno)d - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False  

class Log:
    @staticmethod
    def exception(msg: str, exc_info=True):
        logger.error(msg, exc_info=exc_info, stacklevel=2)

    @staticmethod
    def warning(msg: str, exc_info=False):
        logger.warning(msg, exc_info=exc_info, stacklevel=2)

    @staticmethod
    def info(msg: str, exc_info=False):
        logger.info(msg, exc_info=exc_info, stacklevel=2)