"""S3-compatible storage helpers using presigned URLs."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from settings import settings

logger = logging.getLogger(__name__)


class S3StorageError(RuntimeError):
    """Raised when an S3 operation fails."""


@lru_cache(maxsize=1)
def _get_client() -> Any:
    session = boto3.session.Session(
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )
    return session.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        config=Config(signature_version="s3v4"),
    )


def generate_presigned_upload(key: str, *, expires_in: int = 3600, content_type: str | None = None) -> dict[str, Any]:
    """Generate a presigned POST payload for direct uploads."""
    client = _get_client()
    fields: dict[str, Any] = {"acl": "private"}
    conditions: list[Any] = [{"acl": "private"}]

    if content_type:
        fields["Content-Type"] = content_type
        conditions.append({"Content-Type": content_type})

    try:
        return client.generate_presigned_post(
            settings.S3_BUCKET,
            key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Failed to generate presigned upload for %s", key)
        raise S3StorageError(str(exc)) from exc


def generate_presigned_download(key: str, *, expires_in: int = 3600) -> str:
    """Generate a presigned download URL."""
    client = _get_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Failed to generate presigned download for %s", key)
        raise S3StorageError(str(exc)) from exc


def ensure_bucket_exists() -> None:
    """Ensure the target bucket exists; create it if necessary."""
    client = _get_client()
    try:
        client.head_bucket(Bucket=settings.S3_BUCKET)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchBucket"}:
            params: dict[str, Any] = {"Bucket": settings.S3_BUCKET}
            if settings.S3_REGION and settings.S3_REGION != "us-east-1":
                params["CreateBucketConfiguration"] = {"LocationConstraint": settings.S3_REGION}
            client.create_bucket(**params)
        else:
            logger.exception("Failed to ensure bucket %s", settings.S3_BUCKET)
            raise S3StorageError(str(exc)) from exc
    except BotoCoreError as exc:
        logger.exception("Failed to ensure bucket %s", settings.S3_BUCKET)
        raise S3StorageError(str(exc)) from exc
