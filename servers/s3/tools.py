from __future__ import annotations

import base64
import os
from typing import Annotated, Any

from fastmcp import FastMCP
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    UpstreamError,
    ValidationError,
)
from pydantic import Field

try:
    import aioboto3
except ImportError:
    aioboto3 = None

try:
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    ClientError = None
    NoCredentialsError = None

_MAX_OBJECTS = 1000
_MAX_GET_BYTES = 1_000_000
_MAX_PUT_BYTES = 5_000_000


def _region() -> str:
    return os.environ.get("AWS_REGION", "us-east-1").strip() or "us-east-1"


def _endpoint_url() -> str | None:
    url = os.environ.get("AWS_ENDPOINT_URL", "").strip()
    return url or None


def _session():
    if aioboto3 is None:
        raise ConfigError("aioboto3 is not installed; add extras=[aws]")
    return aioboto3.Session()


def _client(session):
    kwargs: dict[str, Any] = {"region_name": _region()}
    endpoint = _endpoint_url()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return session.client("s3", **kwargs)


def _map_client_error(exc: Exception) -> Exception:
    if ClientError is not None and isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        msg = exc.response.get("Error", {}).get("Message", str(exc))
        if code in {"NoSuchBucket", "NoSuchKey", "404", "NotFound"}:
            return NotFoundError(f"S3 not found: {msg}")
        if code in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403"}:
            return AuthError(f"S3 auth failed: {msg}")
        return UpstreamError(f"S3 error {code}: {msg}")
    if NoCredentialsError is not None and isinstance(exc, NoCredentialsError):
        return ConfigError("AWS credentials not found")
    return UpstreamError(f"S3 request failed: {exc}")


def _clamp(n: int, lo: int, hi: int) -> int:
    if n < lo:
        return lo
    if n > hi:
        return hi
    return n


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_buckets() -> dict[str, Any]:
        """List all S3 buckets accessible with the current credentials."""
        session = _session()
        try:
            async with _client(session) as s3:
                response = await s3.list_buckets()
        except Exception as exc:
            raise _map_client_error(exc) from exc
        buckets = [
            {
                "name": b.get("Name"),
                "creation_date": b["CreationDate"].isoformat() if b.get("CreationDate") else None,
            }
            for b in response.get("Buckets", [])
        ]
        return {"buckets": buckets, "count": len(buckets)}

    @mcp.tool
    async def list_objects(
        bucket: Annotated[str, Field(description="S3 bucket name.")],
        prefix: Annotated[str, Field(description="Key prefix filter.")] = "",
        max_keys: Annotated[int, Field(description="Max objects to return (1-1000).")] = 100,
    ) -> dict[str, Any]:
        """List objects in an S3 bucket, optionally filtered by prefix."""
        if not bucket.strip():
            raise ValidationError("bucket must not be empty")
        session = _session()
        kwargs: dict[str, Any] = {
            "Bucket": bucket,
            "MaxKeys": _clamp(max_keys, 1, _MAX_OBJECTS),
        }
        if prefix:
            kwargs["Prefix"] = prefix
        try:
            async with _client(session) as s3:
                response = await s3.list_objects_v2(**kwargs)
        except Exception as exc:
            raise _map_client_error(exc) from exc
        objects = [
            {
                "key": o.get("Key"),
                "size": o.get("Size"),
                "etag": (o.get("ETag") or "").strip('"'),
                "last_modified": o["LastModified"].isoformat() if o.get("LastModified") else None,
                "storage_class": o.get("StorageClass"),
            }
            for o in response.get("Contents", [])
        ]
        return {
            "bucket": bucket,
            "prefix": prefix,
            "objects": objects,
            "count": len(objects),
            "truncated": response.get("IsTruncated", False),
        }

    @mcp.tool
    async def get_object(
        bucket: Annotated[str, Field(description="S3 bucket name.")],
        key: Annotated[str, Field(description="S3 object key.")],
    ) -> dict[str, Any]:
        """Fetch an S3 object. Returns text if utf-8 decodable, else base64-encoded bytes. Capped at 1MB."""
        if not bucket.strip() or not key.strip():
            raise ValidationError("bucket and key are required")
        session = _session()
        try:
            async with _client(session) as s3:
                response = await s3.get_object(Bucket=bucket, Key=key)
                body_stream = response["Body"]
                data = await body_stream.read(_MAX_GET_BYTES + 1)
        except Exception as exc:
            raise _map_client_error(exc) from exc
        truncated = len(data) > _MAX_GET_BYTES
        if truncated:
            data = data[:_MAX_GET_BYTES]
        try:
            text = data.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = base64.b64encode(data).decode("ascii")
            encoding = "base64"
        return {
            "bucket": bucket,
            "key": key,
            "size": response.get("ContentLength"),
            "content_type": response.get("ContentType"),
            "etag": (response.get("ETag") or "").strip('"'),
            "encoding": encoding,
            "content": text,
            "truncated": truncated,
        }

    @mcp.tool
    async def put_object(
        bucket: Annotated[str, Field(description="S3 bucket name.")],
        key: Annotated[str, Field(description="S3 object key.")],
        content: Annotated[str, Field(description="Object body (utf-8 text).")],
        content_type: Annotated[str, Field(description="Content-Type header.")] = "text/plain",
    ) -> dict[str, Any]:
        """Upload a utf-8 text object to S3. Max body 5MB."""
        if not bucket.strip() or not key.strip():
            raise ValidationError("bucket and key are required")
        body = content.encode("utf-8")
        if len(body) > _MAX_PUT_BYTES:
            raise ValidationError(f"content exceeds {_MAX_PUT_BYTES} byte cap")
        session = _session()
        try:
            async with _client(session) as s3:
                response = await s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=body,
                    ContentType=content_type,
                )
        except Exception as exc:
            raise _map_client_error(exc) from exc
        return {
            "bucket": bucket,
            "key": key,
            "size": len(body),
            "etag": (response.get("ETag") or "").strip('"'),
            "version_id": response.get("VersionId"),
        }
