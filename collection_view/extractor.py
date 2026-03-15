from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .models import ExtractedData

REALM_FILENAME = "client.realm"


class RealmExtractorError(RuntimeError):
    pass


def detect_realm_file(base_dir: Path) -> Path | None:
    realm_path = base_dir / REALM_FILENAME
    return realm_path if realm_path.exists() else None


class RealmExtractor:
    def __init__(self, base_dir: Path, runtime_dir: Path, resource_dir: Path | None = None) -> None:
        self.base_dir = base_dir
        self.runtime_dir = runtime_dir
        self.resource_dir = resource_dir or base_dir
        self.is_frozen = bool(getattr(sys, "frozen", False))
        
        if self.is_frozen:
            self.bundle_dir = self.resource_dir / "extractor_runtime"
        else:
            self.bundle_dir = self.base_dir / "build" / "extractor_runtime"
        
        self.bundle_exe_path = self.bundle_dir / "CollectionRealmExtractor.exe"
        self.output_path = runtime_dir / "extracted.json"

    def extract(self, realm_path: Path) -> ExtractedData:
        if not self.bundle_exe_path.exists():
            raise RealmExtractorError(
                f"提取器不存在: {self.bundle_exe_path}\n"
                "请先运行构建脚本: build_extractor.ps1"
            )
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        command = [str(self.bundle_exe_path), str(realm_path), str(self.output_path)]

        result = subprocess.run(
            command,
            cwd=self.base_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RealmExtractorError(
                "提取器执行失败。\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        try:
            payload = json.loads(self.output_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RealmExtractorError(f"无法读取提取结果: {exc}") from exc

        return ExtractedData.from_dict(payload)
