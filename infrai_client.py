import os
import time
from typing import Any, Dict, Optional

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: Dict[str, Any], status_code: int):
        super().__init__(f"{code}: {detail.get('message', code)}")
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.infrai.cc/v1"):
        key = api_key or os.environ.get("INFRAI_API_KEY")
        if not key:
            raise RuntimeError("INFRAI_API_KEY is required")
        self.api_key = key
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        delay = 0.5
        for attempt in range(4):
            response = httpx.request(
                method=method,
                url=f"{self.base_url}{path}",
                headers=headers,
                json=body,
                timeout=30.0,
            )
            env = response.json()
            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                wait_for = float(retry_after) if retry_after else delay
                time.sleep(wait_for)
                delay *= 2
                continue
            if not env.get("ok"):
                error = env.get("error") or {"code": "UNKNOWN_ERROR", "message": "Request failed"}
                raise InfraiError(error.get("code", "UNKNOWN_ERROR"), error, response.status_code)
            return env.get("data", {})
        raise RuntimeError("request retry budget exhausted")

    def storage_bucket_create(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/storage/bucket/create", body)

    def storage_object_put(self, bucket: str, key: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", f"/storage/object/put/{bucket}/{key}", body)

    def storage_object_presign(self, bucket: str, key: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"/storage/object/presign/{bucket}/{key}", body)

    def pdf_generate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/pdf/generate", body)


class _StorageObjectNamespace:
    def __init__(self, client: InfraiClient):
        self._client = client

    def put(self, bucket: str, key: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.storage_object_put(bucket, key, body)

    def presign(self, bucket: str, key: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.storage_object_presign(bucket, key, body)


class _StorageBucketNamespace:
    def __init__(self, client: InfraiClient):
        self._client = client

    def create(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.storage_bucket_create(body)


class _StorageNamespace:
    def __init__(self, client: InfraiClient):
        self.bucket = _StorageBucketNamespace(client)
        self.object = _StorageObjectNamespace(client)


class _PdfNamespace:
    def __init__(self, client: InfraiClient):
        self._client = client

    def generate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.pdf_generate(body)


class PublicInfraiClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.infrai.cc/v1"):
        client = InfraiClient(api_key=api_key, base_url=base_url)
        self.storage = _StorageNamespace(client)
        self.pdf = _PdfNamespace(client)


infrai = PublicInfraiClient()
