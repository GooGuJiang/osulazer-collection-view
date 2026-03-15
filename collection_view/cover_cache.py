from __future__ import annotations

from pathlib import Path

import requests


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

        headers = {"User-Agent": "osulazer-collection-view/1.0"}
        urls = (
            f"https://assets.ppy.sh/beatmaps/{beatmap_set_id}/covers/raw.jpg",
            f"https://assets.ppy.sh/beatmaps/{beatmap_set_id}/covers/cover.jpg",
        )
        for url in urls:
            try:
                response = requests.get(url, timeout=12, headers=headers)
                if response.ok and response.content:
                    target.write_bytes(response.content)
                    return target
            except requests.RequestException:
                continue

        return None
