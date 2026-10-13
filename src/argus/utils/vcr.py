import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

VCR_DIR = Path("tests/fixtures/vcr")

def get_vcr_mode() -> str:
    """Return the current VCR mode: 'bypass', 'record', or 'replay'."""
    return os.environ.get("ARGUS_VCR_MODE", "bypass").lower()

def _hash_key(key: str) -> str:
    """Generate a consistent hash for a URL or search query."""
    return hashlib.md5(key.encode("utf-8")).hexdigest()

class VCRProxy:
    """Proxy interceptor for recording and replaying deterministic network operations."""

    @staticmethod
    async def fetch(url: str, fetch_func: Callable) -> Any:
        """Intercept a document fetch."""
        from argus.crawler.models import Document
        
        mode = get_vcr_mode()
        if mode == "bypass":
            return await fetch_func()

        cache_dir = VCR_DIR / "fetch"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{_hash_key(url)}.json"

        if mode == "replay":
            if cache_file.exists():
                logger.info(f"[VCR REPLAY] Fetching cached document for: {url}")
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return Document.model_validate(data)
            raise ValueError(f"VCR Replay failed: No fetch cache found for {url} ({cache_file.name})")

        if mode == "record":
            doc = await fetch_func()
            logger.info(f"[VCR RECORD] Saving fetched document for: {url}")
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(doc.model_dump_json(indent=2))
            return doc

        return await fetch_func()

    @staticmethod
    async def search(query_str: str, search_func: Callable) -> Any:
        """Intercept a search query."""
        from argus.search.models import SearchResponse
        
        mode = get_vcr_mode()
        if mode == "bypass":
            return await search_func()

        cache_dir = VCR_DIR / "search"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{_hash_key(query_str)}.json"

        if mode == "replay":
            if cache_file.exists():
                logger.info(f"[VCR REPLAY] Returning cached search for: '{query_str}'")
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return SearchResponse.model_validate(data)
            raise ValueError(f"VCR Replay failed: No search cache found for '{query_str}' ({cache_file.name})")

        if mode == "record":
            response = await search_func()
            logger.info(f"[VCR RECORD] Saving search results for: '{query_str}'")
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(response.model_dump_json(indent=2))
            return response

        return await search_func()
