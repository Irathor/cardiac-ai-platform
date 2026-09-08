"""Bounded file upload reading.

`UploadFile.read()` with no argument buffers the entire file in memory
regardless of size — an authenticated DOCTOR/ANNOTATOR could otherwise upload
an arbitrarily large file and exhaust server memory or MinIO storage (OWASP
API4:2023, Unrestricted Resource Consumption). Reading in bounded chunks and
aborting as soon as the cap is exceeded means memory usage never exceeds the
limit, rather than reading the whole file before checking its size.
"""
from fastapi import UploadFile

MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB — generous for one NIfTI cardiac MRI series
_CHUNK_SIZE = 1024 * 1024


class UploadTooLargeError(ValueError):
    pass


async def read_upload_within_limit(
    file: UploadFile, max_bytes: int = MAX_UPLOAD_SIZE_BYTES
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLargeError(f"file exceeds the {max_bytes}-byte upload limit")
        chunks.append(chunk)
    return b"".join(chunks)
