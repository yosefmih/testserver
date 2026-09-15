import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from .config import Settings

STREAM_CHUNK_BYTES = 1 << 20


@dataclass
class StoredObject:
    size: int
    content_type: str
    chunks: AsyncIterator[bytes]


class Storage:
    def __init__(self, settings: Settings):
        self._bucket = settings.s3_bucket
        self._prefix = settings.s3_prefix.strip("/")
        self._client = boto3.client("s3", endpoint_url=settings.s3_endpoint_url or None)

    def describe(self) -> str:
        return f"s3://{self._bucket}/{self._prefix}"

    def _key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object, Bucket=self._bucket, Key=self._key(key), Body=data, ContentType=content_type
        )

    async def get(self, key: str) -> bytes:
        def read() -> bytes:
            return self._client.get_object(Bucket=self._bucket, Key=self._key(key))["Body"].read()

        return await asyncio.to_thread(read)

    async def open(self, key: str) -> StoredObject:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=self._key(key))
        body = response["Body"]

        async def chunks() -> AsyncIterator[bytes]:
            try:
                while chunk := await asyncio.to_thread(body.read, STREAM_CHUNK_BYTES):
                    yield chunk
            finally:
                body.close()

        return StoredObject(size=response["ContentLength"], content_type=response.get("ContentType", ""), chunks=chunks())

    async def exists(self, key: str) -> bool:
        def head() -> bool:
            try:
                self._client.head_object(Bucket=self._bucket, Key=self._key(key))
            except ClientError:
                return False
            return True

        return await asyncio.to_thread(head)

    async def list_dirs(self, prefix: str) -> list[str]:
        def ls() -> list[str]:
            base = self._key(prefix).rstrip("/") + "/"
            names = []
            for page in self._client.get_paginator("list_objects_v2").paginate(
                Bucket=self._bucket, Prefix=base, Delimiter="/"
            ):
                names.extend(cp["Prefix"].rstrip("/").rsplit("/", 1)[-1] for cp in page.get("CommonPrefixes", []))
            return names

        return await asyncio.to_thread(ls)

    async def delete_prefix(self, prefix: str) -> None:
        def rm() -> None:
            base = self._key(prefix).rstrip("/") + "/"
            for page in self._client.get_paginator("list_objects_v2").paginate(Bucket=self._bucket, Prefix=base):
                keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if keys:
                    self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": keys})

        await asyncio.to_thread(rm)
