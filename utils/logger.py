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
        
        console_handler = logging.StreamHandler()

        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
