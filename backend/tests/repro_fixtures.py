from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.composition import CompositionService, discover_media_tools
from creativeos_db.voice import VoiceService


COMMITTED_HERO_SHA256 = "881ffbcaafc212e49addad08846a5b82761355fa20624253af3477ba33262c5c"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_committed_hero(repo: Path, root: Path) -> Path:
    source = (repo / "app" / "src" / "assets" / "hero.png").resolve()
    if sha256_file(source) != COMMITTED_HERO_SHA256:
        raise AssertionError("committed hero.png checksum changed")
    target = (root / "assets" / "hero.png").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if sha256_file(target) != COMMITTED_HERO_SHA256:
        raise AssertionError("fixture hero copy checksum mismatch")
    return target


def build_render_fixture(root: Path, repo: Path) -> tuple[Path, dict]:
    """Build a deterministic Batch 9-equivalent render fixture in temp storage."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    visual = copy_committed_hero(repo, root)
    db = root / "proof.sqlite3"

    store = CreativeOSStore(db)
    try:
        if store.migrate_to_latest() != 12:
            raise AssertionError("fixture schema migration did not reach v12")
        brand = BrandBrainService(store).load_fleetpilot_fixture()
        campaign = store.create(
            "campaigns",
            {"brand_profile_id": brand["id"], "title": "Reproducible QA fixture"},
        )
        board = store.create(
            "storyboards",
            {"campaign_id": campaign["id"], "title": "Reproducible QA fixture"},
        )
        scene = store.create(
            "scenes",
            {
                "storyboard_id": board["id"],
                "position": 1,
                "title": "Reproducible render",
                "duration_seconds": 2,
                "scene_type": "AI_IMAGE",
                "generation_method": "GENERATIVE",
            },
        )
        ffmpeg, ffprobe = discover_media_tools()
        output_root = root / "generated"
        voice_service = VoiceService(store, output_root / "voice")
        voice_job = voice_service.create_job(
            scene["id"],
            "Control your fleet with confidence",
            "en",
            "mock-ainsley",
        )
        voice = voice_service.run_job(voice_job["id"])

        composition = CompositionService(
            store,
            root,
            output_root,
            ffmpeg,
            ffprobe,
        )
        timeline = composition.create_timeline(
            campaign["id"],
            board["id"],
            [
                {
                    "scene_id": scene["id"],
                    "duration_ms": 2000,
                    "visual_path": str(visual),
                    "audio_path": voice["output_path"],
                    "transition": {"type": "cut"},
                }
            ],
            target_width=640,
            target_height=360,
            aspect_ratio="16:9",
            fps=24,
        )["timeline"]
        render = composition.render_preview(timeline["id"])
        if render["status"] != "SUCCEEDED" or int(render["exit_code"]) != 0:
            raise AssertionError("fixture render did not succeed")
        if not Path(render["output_path"]).is_file():
            raise AssertionError("fixture render output is missing")
        attempts = store.list("render_attempts", {"render_job_id": render["id"]})
        if len(attempts) != 1:
            raise AssertionError("fixture render must have exactly one attempt")
        return db, dict(render)
    finally:
        store.close()
