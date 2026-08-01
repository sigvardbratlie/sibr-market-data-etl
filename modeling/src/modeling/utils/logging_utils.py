import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def add_file_handler(filename='log/app.log',format : str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'):
    if isinstance(filename, str):
        filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
                                    filename=str(filename),
                                    maxBytes=10 * 1024 * 1024,
                                    backupCount=3, 
                                    encoding="utf-8"
                                )
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(format)
    file_handler.setFormatter(formatter)
    logging.root.addHandler(file_handler)

def add_stream_handler(format : str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'):
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(format)
    stream_handler.setFormatter(formatter)
    logging.root.addHandler(stream_handler)

def setup_logging() -> None:
    format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=format)
    add_file_handler(format=format)
    add_stream_handler(format=format)
    