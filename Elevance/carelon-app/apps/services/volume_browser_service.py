"""Volume Browser Service — browse volumes and folders with caching and retry.

All operations run as the logged-in user via X-Forwarded-Access-Token.
Uses direct REST API calls (no SDK) to avoid conflicts with the
DATABRICKS_CLIENT_ID/SECRET env vars injected for SP admin operations.

Features:
- Thread-safe TTL cache (90s) for directory listings
- Retry on HTTP 429 (rate limit) with exponential backoff
- Cache invalidation on folder creation
"""

import os
import time
import threading
import logging
from typing import Dict, Optional
import requests as http_requests

logger = logging.getLogger(__name__)

# --- Config ---
MAX_RETRIES = 3
INITIAL_BACKOFF_SEC = 1.5
CACHE_TTL_SEC = 90

# --- Thread-safe TTL Cache ---
_cache_lock = threading.Lock()
_cache_store = {}  # { key: (data, expiry_time) }


def _cache_get(key):
    with _cache_lock:
        entry = _cache_store.get(key)
        if entry and time.time() < entry[1]:
            return entry[0]
        if entry:
            del _cache_store[key]
    return None


def _cache_set(key, data):
    with _cache_lock:
        _cache_store[key] = (data, time.time() + CACHE_TTL_SEC)


def _cache_invalidate(prefix=''):
    with _cache_lock:
        if not prefix:
            _cache_store.clear()
        else:
            to_del = [k for k in _cache_store if k.startswith(prefix)]
            for k in to_del:
                del _cache_store[k]


def _get_host():
    """Get the Databricks workspace host with https:// scheme."""
    host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'
    return host


def _user_headers(user_token: str) -> dict:
    """Build auth headers using the user's forwarded OAuth token."""
    return {'Authorization': f'Bearer {user_token}'}


class VolumeBrowserService:
    """Provides Volume folder browsing with caching and rate-limit retry."""

    def list_directory(self, volume_path: str, subfolder: str = '',
                       user_token: Optional[str] = None) -> Dict:
        """List contents of a directory within a volume.

        - Checks cache first (90s TTL)
        - Retries up to 3 times on HTTP 429
        - Caches successful results
        """
        if not user_token or not user_token.strip():
            return {'items': [], 'error': 'User access token not available.'}

        host = _get_host()
        full_path = volume_path.rstrip('/')
        if subfolder:
            full_path = f"{full_path}/{subfolder.strip('/')}"

        # Check cache
        cache_key = f"dir:{full_path}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        api_path = full_path.lstrip('/')
        url = f"{host}/api/2.0/fs/directories/{api_path}"
        last_error = ''

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = http_requests.get(
                    url, headers=_user_headers(user_token), timeout=30,
                )

                # Handle rate limit
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get('Retry-After', INITIAL_BACKOFF_SEC * attempt))
                    logger.warning(f"429 on {full_path}, attempt {attempt}/{MAX_RETRIES}, wait {retry_after}s")
                    if attempt < MAX_RETRIES:
                        time.sleep(retry_after)
                        continue
                    return {'items': [], 'error': 'Rate limit exceeded. Please wait a moment and try again.'}

                # Non-200 error
                if resp.status_code != 200:
                    error_msg = resp.text[:300]
                    logger.error(f"List directory failed ({resp.status_code}): {error_msg}")
                    return {'items': [], 'error': f'Failed to list directory (HTTP {resp.status_code}): {error_msg}'}

                # Success — parse and cache
                data = resp.json()
                items = []
                for entry in data.get('contents', []):
                    name = entry.get('name', entry.get('path', '').rstrip('/').split('/')[-1])
                    is_dir = entry.get('is_directory', False)
                    items.append({
                        'name': name,
                        'path': f"{full_path}/{name}",
                        'is_directory': is_dir,
                        'size': entry.get('file_size', 0) if not is_dir else 0,
                        'last_modified': entry.get('last_modified', ''),
                    })

                result = {'items': items}
                _cache_set(cache_key, result)
                return result

            except Exception as e:
                last_error = str(e)
                logger.error(f"list_directory attempt {attempt} failed: {last_error}")
                if attempt < MAX_RETRIES:
                    time.sleep(INITIAL_BACKOFF_SEC * attempt)
                    continue

        return {'items': [], 'error': f'Failed after {MAX_RETRIES} attempts: {last_error}'}

    def create_folder(self, volume_path: str, folder_name: str,
                      subfolder: str = '', user_token: Optional[str] = None) -> Dict:
        """Create a new folder in the volume.

        Invalidates parent directory cache on success.
        Retries on 429.
        """
        if not user_token or not user_token.strip():
            return {'success': False, 'path': '', 'error': 'User access token not available.'}

        host = _get_host()
        base = volume_path.rstrip('/')
        if subfolder:
            base = f"{base}/{subfolder.strip('/')}"
        new_path = f"{base}/{folder_name}"

        api_path = new_path.lstrip('/')
        url = f"{host}/api/2.0/fs/directories/{api_path}"

        logger.info(f"Creating folder: {new_path}")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = http_requests.put(
                    url, headers=_user_headers(user_token), timeout=30,
                )

                if resp.status_code == 429:
                    if attempt < MAX_RETRIES:
                        time.sleep(INITIAL_BACKOFF_SEC * attempt)
                        continue
                    return {'success': False, 'path': '', 'error': 'Rate limit exceeded.'}

                if resp.status_code in (200, 201, 204):
                    # Invalidate parent directory cache
                    _cache_invalidate(f"dir:{base}")
                    return {'success': True, 'path': new_path, 'error': ''}
                else:
                    error_msg = resp.text[:300]
                    logger.error(f"Create folder failed ({resp.status_code}): {error_msg}")
                    return {'success': False, 'path': '', 'error': f'HTTP {resp.status_code}: {error_msg}'}

            except Exception as e:
                logger.error(f"create_folder attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(INITIAL_BACKOFF_SEC * attempt)
                    continue
                return {'success': False, 'path': '', 'error': str(e)}

        return {'success': False, 'path': '', 'error': 'Failed after retries.'}
