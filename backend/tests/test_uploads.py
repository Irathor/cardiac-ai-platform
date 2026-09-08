"""Bounded upload reading — see docs/architecture.md's security notes.
An unbounded `UploadFile.read()` lets an authenticated user exhaust server
memory/storage with an arbitrarily large file (OWASP API4:2023)."""
import io

import pytest
from starlette.datastructures import UploadFile

from app.core.uploads import UploadTooLargeError, read_upload_within_limit


def _upload(data: bytes) -> UploadFile:
    return UploadFile(filename="test.nii.gz", file=io.BytesIO(data))


@pytest.mark.asyncio
async def test_reads_a_file_within_the_limit():
    result = await read_upload_within_limit(_upload(b"x" * 100), max_bytes=1000)
    assert result == b"x" * 100


@pytest.mark.asyncio
async def test_rejects_a_file_over_the_limit():
    with pytest.raises(UploadTooLargeError):
        await read_upload_within_limit(_upload(b"x" * 2000), max_bytes=1000)


@pytest.mark.asyncio
async def test_exact_limit_is_accepted():
    result = await read_upload_within_limit(_upload(b"x" * 1000), max_bytes=1000)
    assert len(result) == 1000


@pytest.mark.asyncio
async def test_one_byte_over_the_limit_is_rejected():
    with pytest.raises(UploadTooLargeError):
        await read_upload_within_limit(_upload(b"x" * 1001), max_bytes=1000)
