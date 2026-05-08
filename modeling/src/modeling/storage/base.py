import os 
import logging
from abc import ABC, abstractmethod

from networkx import config

logger = logging.getLogger(__name__)

class BaseStorageManager:
    def __init__(self):
        pass

    @abstractmethod
    def save_file(self, 
                        content: bytes, 
                        path : str, 
                        metadata : dict = None) -> str | None:
        pass

    @abstractmethod
    async def save_files(self, 
                                 attachments: list, 
                                 ) -> bool:
        pass

    @abstractmethod
    def read_file(self, path : str) -> bytes:
        pass

    @abstractmethod
    def read_files(self, paths: list[str]) -> dict[str, bytes | None]:
        pass

    @abstractmethod
    def delete_file(self, path : str) -> None:
        pass

    