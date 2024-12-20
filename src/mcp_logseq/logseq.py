import requests
from typing import Any, Dict, List, Optional

class LogSeq():
    def __init__(
            self,
            api_token: str,
            api_url: str = "http://localhost:12315",
            verify_ssl: bool = False,
        ):
        self.api_token = api_token
        self.api_url = api_url
        self.verify_ssl = verify_ssl
        self.timeout = (3, 6)

    def _get_headers(self) -> dict:
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }
        return headers

    def _safe_call(self, f) -> Any:
        try:
            return f()
        except requests.HTTPError as e:
            error_data = e.response.json() if e.response.content else {}
            message = error_data.get('message', '<unknown>')
            raise Exception(f"Error: {message}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def list_graphs(self) -> List[Dict[str, Any]]:
        url = f"{self.api_url}/graphs"
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    def list_pages(self, graph_name: Optional[str] = None) -> List[Dict[str, Any]]:
        url = f"{self.api_url}/pages"
        if graph_name:
            url += f"?graph={graph_name}"
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    def get_page_content(self, page_name: str, graph_name: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.api_url}/pages/{page_name}"
        if graph_name:
            url += f"?graph={graph_name}"
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    def search(self, query: str) -> List[Dict[str, Any]]:
        url = f"{self.api_url}/search"
        
        def call_fn():
            response = requests.post(
                url, 
                headers=self._get_headers(),
                json={"q": query},
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    def create_page(self, title: str, content: str, graph_name: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.api_url}/pages"
        if graph_name:
            url += f"?graph={graph_name}"
        
        def call_fn():
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"title": title, "content": content},
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    def update_page(self, page_name: str, content: str, graph_name: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.api_url}/pages/{page_name}"
        if graph_name:
            url += f"?graph={graph_name}"
        
        def call_fn():
            response = requests.put(
                url,
                headers=self._get_headers(),
                json={"content": content},
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    def delete_page(self, page_name: str, graph_name: Optional[str] = None) -> None:
        url = f"{self.api_url}/pages/{page_name}"
        if graph_name:
            url += f"?graph={graph_name}"
        
        def call_fn():
            response = requests.delete(
                url,
                headers=self._get_headers(),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
