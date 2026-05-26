import os
import logging


def setup_logger():

    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger("agentic_debugger")
    logger.setLevel(logging.INFO)

    if not logger.handlers:

        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
            )
        
        file_handler = logging.FileHandler(
            "logs/system.log"
            )

        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    return logger
