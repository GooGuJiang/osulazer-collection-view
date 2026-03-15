from __future__ import annotations

import asyncio
from pathlib import Path

import httpx


class CoverCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cover_path(self, beatmap_set_id: int | None) -> Path | None:
        if not beatmap_set_id or beatmap_set_id <= 0:
            return None

        target = self.cache_dir / f"{beatmap_set_id}.jpg"
        if target.exists():
            return target

        try:
            return asyncio.run(self._download_cover(beatmap_set_id, target))
        except Exception:
            return None

    async def _download_cover(self, beatmap_set_id: int, target: Path) -> Path | None:
        headers = {"User-Agent": "osulazer-collection-view/1.0"}
        urls = (
            f"https://assets.ppy.sh/beatmaps/{beatmap_set_id}/covers/raw.jpg",
            f"https://assets.ppy.sh/beatmaps/{beatmap_set_id}/covers/cover.jpg",
        )
        
        async with httpx.AsyncClient(timeout=12.0) as client:
            for url in urls:
                try:
                    response = await client.get(url, headers=headers)
                    if response.status_code == 200 and response.content:
                        target.write_bytes(response.content)
                        return target
                except httpx.HTTPError:
                    continue
        
        return None
