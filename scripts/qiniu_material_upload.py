"""Qiniu adapter for operator-published material images (optional SDK dependency)."""
from __future__ import annotations

import io
import os
from typing import Any
from urllib.parse import urlsplit


class QiniuUploadClient:
    def __init__(self, *, bucket: str, access_key: str, secret_key: str,
                 upload_host: str, private: bool = True):
        from qiniu import Auth, Region
        parsed = urlsplit(upload_host)
        if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.qiniup.com'):
            raise ValueError('Qiniu uploads require an official HTTPS upload endpoint')
        self.bucket = bucket
        self.private = private
        self.auth = Auth(access_key, secret_key)
        self.regions = [Region(up_host=upload_host, scheme='https')]

    def storage_metadata(self, key: str) -> dict:
        return {'provider': 'qiniu', 'bucket': self.bucket, 'key': key, 'private': self.private}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> Any:
        from qiniu import put_data
        from qiniu.utils import etag_stream
        if Bucket != self.bucket:
            raise ValueError('Configured Qiniu bucket does not match upload destination')
        token = self.auth.upload_token(Bucket, Key, 3600, {'fsizeLimit': len(Body)})
        result, info = put_data(token, Key, Body, mime_type=ContentType,
                                fname=Key.rsplit('/', 1)[-1], regions=self.regions)
        if info.status_code != 200 or not result:
            # SDK response/request details can contain credentials; expose only status.
            raise RuntimeError(f'Qiniu upload failed (HTTP {info.status_code})')
        if result.get('key') != Key or result.get('hash') != etag_stream(io.BytesIO(Body)):
            raise RuntimeError('Qiniu upload checksum or object key mismatch')
        return result


def qiniu_client_from_env(bucket: str) -> QiniuUploadClient:
    return QiniuUploadClient(bucket=bucket, access_key=os.environ['QINIU_ACCESS_KEY'],
                             secret_key=os.environ['QINIU_SECRET_KEY'],
                             upload_host=os.environ['QINIU_UPLOAD_HOST'],
                             private=os.getenv('QINIU_PRIVATE', 'true').lower() == 'true')
