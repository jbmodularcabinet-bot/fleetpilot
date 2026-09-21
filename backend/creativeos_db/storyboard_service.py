from __future__ import annotations
import json
from typing import Any
from .storyboard import validate_scene, rollup, next_version_number
from .store import CreativeOSStore

class StoryboardService:
    def __init__(self, store: CreativeOSStore): self.store = store
    def list_scenes(self, storyboard_id: str) -> list[dict[str, Any]]:
        return self.store.list("scenes", {"storyboard_id": storyboard_id})
    def create_scene(self, storyboard_id: str, values: dict[str, Any]) -> dict[str, Any]:
        data = {"storyboard_id": storyboard_id, **values}; validate_scene(data)
        return self.store.create("scenes", data)
    def update_scene(self, scene_id: str, values: dict[str, Any], explicit: bool=False) -> dict[str, Any]:
        current = self.store.get("scenes", scene_id)
        if (current.get("locked") or current.get("approval_state")=="APPROVED") and not explicit:
            raise ValueError("locked or approved scene requires explicit edit")
        merged = {**current, **values}; validate_scene(merged)
        return self.store.update("scenes", scene_id, values)
    def delete_scene(self, scene_id: str, explicit: bool=False) -> None:
        scene = self.store.get("scenes", scene_id)
        if (scene.get("locked") or scene.get("approval_state")=="APPROVED") and not explicit:
            raise ValueError("locked or approved scene requires explicit delete")
        self.store.delete("scenes", scene_id)
    def reorder(self, storyboard_id: str, ordered_ids: list[str]) -> list[dict[str, Any]]:
        scenes = self.list_scenes(storyboard_id)
        by_id = {s["id"]:s for s in scenes}
        if set(ordered_ids) != set(by_id): raise ValueError("reorder must include every scene exactly once")
        with self.store.conn:
            for i,sid in enumerate(ordered_ids,1):
                self.store.conn.execute("UPDATE scenes SET position=? WHERE id=?", (-i,sid))
            for i,sid in enumerate(ordered_ids,1):
                self.store.conn.execute("UPDATE scenes SET position=? WHERE id=?", (i,sid))
        return self.list_scenes(storyboard_id)
    def duplicate_scene(self, scene_id: str) -> dict[str, Any]:
        scene=self.store.get("scenes",scene_id); board=scene["storyboard_id"]
        scenes=self.list_scenes(board); pos=max(int(s["position"]) for s in scenes)+1
        copy={k:v for k,v in scene.items() if k not in {"id","created_at","updated_at"}}
        copy.update({"position":pos,"title":f'{scene["title"]} Copy',"locked":0,"approval_state":"DRAFT","status":"DRAFT"})
        return self.create_scene(board,copy)
    def set_lock(self, scene_id: str, locked: bool) -> dict[str, Any]:
        return self.store.update("scenes",scene_id,{"locked":int(locked)})
    def set_approval(self, scene_id: str, approved: bool) -> dict[str, Any]:
        return self.store.update("scenes",scene_id,{"approval_state":"APPROVED" if approved else "DRAFT"})
    def set_status(self, scene_id: str, status: str) -> dict[str, Any]:
        return self.update_scene(scene_id,{"status":status},explicit=True)
    def create_version(self, scene_id: str, source_type: str, provider: str="", model: str="", prompt: str="", assets: list[str]|None=None, output_path: str|None=None, cost_estimate_cents: int=0) -> dict[str, Any]:
        scene=self.store.get("scenes",scene_id)
        versions=self.store.list("scene_versions",{"scene_id":scene_id})
        for row in versions:
            if row.get("is_selected"): self.store.update("scene_versions",row["id"],{"is_selected":0})
        created=self.store.create("scene_versions",{
            "scene_id":scene_id,"version_number":next_version_number(versions),"source_type":source_type,
            "provider":provider,"model":model,"prompt":prompt,"asset_refs_json":assets or [],
            "output_path":output_path,"cost_estimate_cents":cost_estimate_cents,
            "qa_state":scene.get("qa_state","PENDING"),"approval_state":"DRAFT","is_selected":1,"is_approved":0,
        })
        self.store.update("scenes",scene_id,{"selected_version_id":created["id"]})
        return created
    def approve_version(self, version_id: str) -> dict[str, Any]:
        version=self.store.get("scene_versions",version_id)
        for row in self.store.list("scene_versions",{"scene_id":version["scene_id"]}):
            self.store.update("scene_versions",row["id"],{"is_approved":0,"approval_state":"DRAFT"})
        approved=self.store.update("scene_versions",version_id,{"is_approved":1,"approval_state":"APPROVED"})
        self.store.update("scenes",version["scene_id"],{"approved_version_id":version_id})
        return approved
    def rollup(self, storyboard_id: str) -> dict[str, int]:
        return rollup(self.list_scenes(storyboard_id))
    def split_scene(self, scene_id: str) -> tuple[dict[str, Any],dict[str, Any]]:
        scene=self.store.get("scenes",scene_id)
        if scene.get("locked") or scene.get("approval_state")=="APPROVED": raise ValueError("locked or approved scene cannot be split")
        first=max(1,int(scene["duration_seconds"])//2); second=max(1,int(scene["duration_seconds"])-first)
        self.store.update("scenes",scene_id,{"duration_seconds":first})
        duplicate=self.duplicate_scene(scene_id)
        duplicate=self.store.update("scenes",duplicate["id"],{"duration_seconds":second})
        return self.store.get("scenes",scene_id),duplicate
    def merge_scenes(self, first_id: str, second_id: str) -> dict[str, Any]:
        a=self.store.get("scenes",first_id); b=self.store.get("scenes",second_id)
        if a["storyboard_id"]!=b["storyboard_id"]: raise ValueError("scenes must belong to same storyboard")
        if a.get("locked") or b.get("locked") or a.get("approval_state")=="APPROVED" or b.get("approval_state")=="APPROVED":
            raise ValueError("locked or approved scenes cannot be merged")
        merged=self.store.update("scenes",first_id,{"duration_seconds":int(a["duration_seconds"])+int(b["duration_seconds"]),"script":f'{a.get("script","")} {b.get("script","")}'.strip()})
        self.store.delete("scenes",second_id)
        return merged
