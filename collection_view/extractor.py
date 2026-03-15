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
        self.project_dir = self.resource_dir / "extractor"
        self.project_file = self.project_dir / "CollectionRealmExtractor.csproj"
        self.build_dir = self.project_dir / "bin" / "Release" / "net9.0"
        self.dll_path = self.build_dir / "CollectionRealmExtractor.dll"
        self.bundle_dir = self.resource_dir / "extractor_runtime"
        self.bundle_exe_path = self.bundle_dir / "CollectionRealmExtractor.exe"
        self.output_path = runtime_dir / "extracted.json"

    def ensure_built(self) -> None:
        if self.is_frozen:
            if not self.bundle_exe_path.exists():
                raise RealmExtractorError(f"打包提取器不存在: {self.bundle_exe_path}")
            return

        if not self.project_file.exists():
            raise RealmExtractorError(f"提取器项目不存在: {self.project_file}")

        should_build = not self.dll_path.exists()
        if not should_build:
            source_files = list(self.project_dir.rglob("*.cs"))
            source_files.append(self.project_file)

            fody_file = self.project_dir / "FodyWeavers.xml"
            if fody_file.exists():
                source_files.append(fody_file)

            latest_source = max(path.stat().st_mtime for path in source_files)
            should_build = latest_source > self.dll_path.stat().st_mtime

        if not should_build:
            return

        result = subprocess.run(
            ["dotnet", "build", str(self.project_file), "-c", "Release"],
            cwd=self.base_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RealmExtractorError(
                "提取器编译失败。\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

    def extract(self, realm_path: Path) -> ExtractedData:
        self.ensure_built()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        command = (
            [str(self.bundle_exe_path), str(realm_path), str(self.output_path)]
            if self.is_frozen
            else ["dotnet", str(self.dll_path), str(realm_path), str(self.output_path)]
        )

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
