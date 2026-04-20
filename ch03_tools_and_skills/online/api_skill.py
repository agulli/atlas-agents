import requests

class RestAPISkill:
    """Takes a generic REST OpenAPI endpoint and wraps it safely for an agent."""
    def __init__(self, base_url, headers):
        self.base_url = base_url
        self.headers = headers
        
    def execute(self, endpoint, method="GET", payload=None):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            if method == "GET":
                res = requests.get(url, headers=self.headers, timeout=5)
            else:
                res = requests.post(url, json=payload, headers=self.headers, timeout=5)
            res.raise_for_status()
            
            # Truncate large JSON responses to protect context window
            data = str(res.json())
            return data[:2000] + "...[TRUNCATED]" if len(data) > 2000 else data
        except Exception as str_e:
            return f"API Call Failed: {str(str_e)}"\n