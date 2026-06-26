"""Volume service — file operations with Databricks Unity Catalog Volumes.

All operations run as the logged-in user via X-Forwarded-Access-Token.
Uses direct REST API calls (no SDK) to avoid conflicts with the
DATABRICKS_CLIENT_ID/SECRET env vars injected for SP admin operations.

The user's forwarded OAuth token has 'files' scope from user_api_scopes config.
"""

import io
import os
import logging
import pandas as pd
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from flask import current_app
import requests as http_requests

logger = logging.getLogger(__name__)


def _get_host():
    """Get the Databricks workspace host with https:// scheme."""
    host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'
    return host


def _user_headers(user_token: str, content_type: str = 'application/json') -> dict:
    """Build auth headers using the user's forwarded OAuth token."""
    headers = {'Authorization': f'Bearer {user_token}'}
    if content_type:
        headers['Content-Type'] = content_type
    return headers


class VolumeService:
    """Handles all file operations with Databricks Volumes as the logged-in user."""

    def _get_volume_path(self, path: Optional[str] = None) -> str:
        """Resolve the base volume path."""
        if path:
            return path
        return current_app.config.get('VOLUME_PATH', '/Volumes/aw_serverless_stable_catalog/carelon/dxutility')

    def _validate_token(self, user_token: str):
        """Raise ValueError if no valid user token provided."""
        if not user_token or not user_token.strip():
            raise ValueError(
                "User access token not available. "
                "Ensure the app has 'files' scope configured under User Authorization."
            )

    def write_tokenized_file(self, df: pd.DataFrame, original_filename: str,
                             file_type: str, delimiter: str = ',',
                             volume_path: Optional[str] = None,
                             user_token: str = '') -> str:
        """Write tokenized DataFrame to Volume as the logged-in user."""
        self._validate_token(user_token)
        base_path = self._get_volume_path(volume_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = os.path.splitext(original_filename)[0]
        output_filename = f"{base_name}_tokenized_{timestamp}.{file_type}"
        output_path = f"{base_path}/{output_filename}"

        # Serialize DataFrame to bytes
        buffer = io.BytesIO()
        if file_type in ('csv', 'tsv'):
            df.to_csv(buffer, index=False, sep=delimiter)
        else:
            df.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)

        # Upload via REST API
        self._upload_bytes(output_path, buffer.read(), user_token, overwrite=True)
        logger.info(f"Written to Volume: {output_path} ({len(df)} rows, as user)")
        return output_path

    def _upload_bytes(self, file_path: str, data: bytes, user_token: str, overwrite: bool = False):
        """Upload raw bytes to a Volume path via Files API."""
        host = _get_host()
        api_path = file_path.lstrip('/')
        url = f"{host}/api/2.0/fs/files/{api_path}"

        headers = {
            'Authorization': f'Bearer {user_token}',
            'Content-Type': 'application/octet-stream',
        }
        if overwrite:
            headers['Overwrite'] = 'true'

        resp = http_requests.put(url, headers=headers, data=data, timeout=120)
        if resp.status_code not in (200, 201, 204):
            raise Exception(f"Upload failed (HTTP {resp.status_code}): {resp.text[:300]}")

    def list_files(self, path: Optional[str] = None, user_token: str = '') -> List[Dict]:
        """List files in the Volume directory as the logged-in user."""
        base_path = self._get_volume_path(path)

        try:
            self._validate_token(user_token)
            host = _get_host()
            api_path = base_path.lstrip('/')
            url = f"{host}/api/2.0/fs/directories/{api_path}"

            resp = http_requests.get(
                url,
                headers=_user_headers(user_token, content_type=''),
                timeout=30,
            )

            if resp.status_code != 200:
                logger.error(f"List files failed ({resp.status_code}): {resp.text[:300]}")
                return []

            data = resp.json()
            files = []
            for entry in data.get('contents', []):
                name = entry.get('name', entry.get('path', '').rstrip('/').split('/')[-1])
                is_dir = entry.get('is_directory', False)
                files.append({
                    'name': name,
                    'path': entry.get('path', ''),
                    'size': entry.get('file_size', 0) or 0,
                    'modified': entry.get('last_modified', ''),
                    'type': 'DIR' if is_dir else (name.rsplit('.', 1)[-1].upper() if '.' in name else 'FILE'),
                    'is_directory': is_dir,
                })
            return files
        except ValueError as e:
            logger.error(f"No user token for list_files: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to list files at {base_path}: {e}")
            return []

    def download_file(self, file_path: str, user_token: str = '') -> Tuple[io.BytesIO, str]:
        """Download a file from Volume as the logged-in user."""
        self._validate_token(user_token)
        filename = file_path.split('/')[-1]

        host = _get_host()
        api_path = file_path.lstrip('/')
        url = f"{host}/api/2.0/fs/files/{api_path}"

        resp = http_requests.get(
            url,
            headers=_user_headers(user_token, content_type=''),
            timeout=120,
        )

        if resp.status_code != 200:
            raise Exception(f"Download failed (HTTP {resp.status_code}): {resp.text[:300]}")

        buffer = io.BytesIO(resp.content)
        return buffer, filename

    def delete_file(self, file_path: str, user_token: str = '') -> None:
        """Delete a file from the Volume as the logged-in user."""
        self._validate_token(user_token)

        host = _get_host()
        api_path = file_path.lstrip('/')
        url = f"{host}/api/2.0/fs/files/{api_path}"

        resp = http_requests.delete(
            url,
            headers=_user_headers(user_token, content_type=''),
            timeout=30,
        )

        if resp.status_code not in (200, 204):
            raise Exception(f"Delete failed (HTTP {resp.status_code}): {resp.text[:300]}")

        logger.info(f"Deleted from Volume: {file_path} (as user)")

    def read_preview(self, file_path: str, nrows: int = 50, user_token: str = '') -> Dict:
        """Read first N rows of a file for preview as the logged-in user."""
        filename = file_path.split('/')[-1]
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

        buffer, _ = self.download_file(file_path, user_token)
        if ext in ('csv', 'tsv'):
            sep = '\t' if ext == 'tsv' else ','
            df = pd.read_csv(buffer, nrows=nrows, sep=sep, dtype=str)
        elif ext in ('xlsx', 'xls'):
            df = pd.read_excel(buffer, nrows=nrows, dtype=str)
        else:
            raise ValueError(f"Cannot preview file type: {ext}")

        return {
            'columns': list(df.columns),
            'rows': df.values.tolist(),
            'total_rows': nrows,
        }
