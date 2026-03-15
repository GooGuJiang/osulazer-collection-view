from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
import webview

from .cover_cache import CoverCache
from .extractor import REALM_FILENAME, RealmExtractor, detect_realm_file
from .exporter import export_current_view
from .models import ExtractedData


class API:
    def __init__(self):
        source_dir = Path(__file__).resolve().parent.parent
        self.resource_dir = Path(getattr(sys, "_MEIPASS", source_dir)).resolve()
        self.base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else source_dir
        self.runtime_dir = self.base_dir / "runtime"
        self.cover_dir = self.runtime_dir / "covers"
        self.cache_file = self.runtime_dir / "cache.json"
        
        self.extractor = RealmExtractor(self.base_dir, self.runtime_dir, resource_dir=self.resource_dir)
        self.cover_cache = CoverCache(self.cover_dir)
        
        self.data: ExtractedData | None = None
        self.detected_realm: Path | None = None
        self.cached_collections = None

    def load_cache(self):
        if self.cache_file.exists():
            try:
                self.cached_collections = json.loads(self.cache_file.read_text(encoding="utf-8"))
            except Exception:
                self.cached_collections = None

    def save_cache(self, collections):
        try:
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(collections, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def refresh_detected_realm(self):
        self.detected_realm = detect_realm_file(self.base_dir)
        self.load_cache()
        
        if self.cached_collections:
            status_suffix = "；已加载缓存数据，可直接使用或点击'加载'重新解析。"
        else:
            status_suffix = "，可以点击'加载'开始解析。" if self.detected_realm else "；当前状态：未检测到可用数据库。"
        
        if self.detected_realm:
            return {
                "detected": True,
                "status": f"请将 {REALM_FILENAME} 手动复制到当前文件夹：{self.base_dir}；当前状态：已检测到 {REALM_FILENAME}" + status_suffix,
                "cached": self.cached_collections
            }
        return {
            "detected": False,
            "status": f"请将 {REALM_FILENAME} 手动复制到当前文件夹：{self.base_dir}" + status_suffix,
            "cached": self.cached_collections
        }

    def load_realm(self):
        if not self.detected_realm:
            return {"success": False, "error": f"请先把 {REALM_FILENAME} 复制到当前目录。"}
        
        try:
            self.data = self.extractor.extract(self.detected_realm)
            collections = []
            for col in self.data.collections:
                items_by_mode = {}
                for mode in ["osu", "taiko", "ctb", "mania"]:
                    mode_items = col.items_for_mode(mode)
                    items_by_mode[mode] = [self._serialize_item(item) for item in mode_items]
                
                collections.append({
                    "name": col.name,
                    "total_count": col.total_count,
                    "items": items_by_mode
                })
            
            self.save_cache(collections)
            
            return {
                "success": True,
                "collections": collections,
                "status": f"请将 {REALM_FILENAME} 手动复制到当前文件夹：{self.base_dir}；当前状态：加载完成，当前读取 {self.detected_realm.name}。"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _serialize_item(self, item):
        return {
            "name_original": item.name_original,
            "star_rating": item.star_rating_text or "-",
            "bid": item.bid_text or "-",
            "sid": item.sid_text or "-",
            "difficulty_name": item.difficulty_name or "-",
            "mapper": item.mapper or "-",
            "mode": item.mode,
            "cs": item.cs_text or "-",
            "od": item.od_text or "-",
            "ar": item.ar_text or "-",
            "hp": item.hp_text or "-",
            "note_count": item.note_count_text or "-",
            "length": item.length_text or "-",
            "bpm": item.bpm_text or "-",
            "status": item.status_text or "-",
            "artist": item.artist_unicode or item.artist or "-",
            "name": item.name,
            "md5": item.md5 or "-",
            "missing": item.missing,
            "beatmap_set_id": item.beatmap_set_id
        }

    def get_cover(self, beatmap_set_id):
        if beatmap_set_id is None:
            return {"success": False}
        
        cover_path = self.cover_cache.get_cover_path(beatmap_set_id)
        if cover_path and cover_path.exists():
            try:
                img_data = base64.b64encode(cover_path.read_bytes()).decode('utf-8')
                return {"success": True, "path": f"data:image/jpeg;base64,{img_data}"}
            except Exception:
                return {"success": False}
        return {"success": False}

    def export_view(self, collection_name, mode, items, visible_columns):
        try:
            from tkinter import filedialog
            import tkinter as tk
            
            root = tk.Tk()
            root.withdraw()
            
            default_name = f"{collection_name}_{mode}.xlsx".replace("/", "_").replace("\\", "_")
            path = filedialog.asksaveasfilename(
                title="导出当前列表",
                defaultextension=".xlsx",
                filetypes=[("Excel 文件", "*.xlsx")],
                initialfile=default_name
            )
            root.destroy()
            
            if not path:
                return {"success": False, "error": "取消导出"}
            
            column_labels = {
                "name_original": "名称（原语言）",
                "star_rating": "难度",
                "bid": "BID",
                "artist": "艺术家（原语言）",
                "difficulty_name": "难度名",
                "mapper": "谱师",
                "mode": "模式",
                "sid": "SID",
                "cs": "CS",
                "od": "OD",
                "ar": "AR",
                "hp": "HP",
                "note_count": "Note数",
                "length": "长度",
                "bpm": "BPM",
                "status": "状态",
                "name": "名称",
                "md5": "MD5"
            }
            
            headers = [column_labels.get(col, col) for col in visible_columns]
            rows = [[item.get(col, "-") for col in visible_columns] for item in items]
            
            export_current_view(Path(path), sheet_name=collection_name, headers=headers, rows=rows)
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}


def launch():
    api = API()
    html_path = str(Path(__file__).parent / "index.html")
    is_dev = not getattr(sys, "frozen", False)
    
    window = webview.create_window(
        "osu! 收藏夹查看器",
        html_path,
        js_api=api,
        width=1540,
        height=940,
        min_size=(1280, 800)
    )
    
    if is_dev:
        webview.start(debug=True)
    else:
        webview.start()
