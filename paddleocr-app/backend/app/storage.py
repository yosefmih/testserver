import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Protocol

from .config import Settings


class Storage(Protocol):
    def describe(self) -> str: ...
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def exists(self, key: str) -> bool: ...
    async def list_dirs(self, prefix: str) -> list[str]: ...
    async def delete_prefix(self, prefix: str) -> None: ...


def open_storage(settings: Settings) -> Storage:
    if settings.s3_bucket:
        return S3Storage(settings.s3_bucket, settings.s3_prefix)
    return LocalStorage(Path(settings.local_data_dir))


class S3Storage:
    def __init__(self, bucket: str, prefix: str):
        import boto3

        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._client = boto3.client("s3")

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

    async def exists(self, key: str) -> bool:
        def head() -> bool:
            try:
                self._client.head_object(Bucket=self._bucket, Key=self._key(key))
            except self._client.exceptions.ClientError:
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


class LocalStorage:
    def __init__(self, root: Path):
        self._root = root
        root.mkdir(parents=True, exist_ok=True)

    def describe(self) -> str:
        return f"local:{self._root.resolve()}"

    def _path(self, key: str) -> Path:
        return self._root / key

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        def write() -> None:
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as tmp:
                tmp.write(data)
            Path(tmp.name).replace(path)

        await asyncio.to_thread(write)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    async def list_dirs(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.is_dir():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir())

    async def delete_prefix(self, prefix: str) -> None:
        await asyncio.to_thread(shutil.rmtree, self._path(prefix), True)
