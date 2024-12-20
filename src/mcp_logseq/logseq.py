import requests
import logging
from typing import Any

logger = logging.getLogger("mcp-logseq")

class LogSeq():
    def __init__(
            self, 
            api_key: str,
            host: str = "127.0.0.1",
            port: int = 12315,
            verify_ssl: bool = False,
        ):
        self.api_key = api_key
        self.host = host
        self.port = port
        self.verify_ssl = verify_ssl
        self.timeout = (3, 6)
        logger.debug(f"LogSeq client initialized with host={host}, port={port}")

    def get_base_url(self) -> str:
        url = f'http://{self.host}:{self.port}/api'
        logger.debug(f"Base URL: {url}")
        return url
    
    def _get_headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def create_page(self, title: str, content: str) -> Any:
        url = self.get_base_url()
        logger.info(f"Creating page '{title}'")
        
        payload = {
            "method": "logseq.Editor.insertBlock",
            "args": [
                title,
                content,
                {"isPageBlock": True}
            ]
        }
        logger.debug(f"Request payload: {payload}")

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response content: {response.text}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error creating page: {str(e)}")
            raise
