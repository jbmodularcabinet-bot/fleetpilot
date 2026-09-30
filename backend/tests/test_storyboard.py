import tempfile, unittest
from pathlib import Path
from creativeos_db import CreativeOSStore
from creativeos_db.storyboard import validate_scene, rollup, next_version_number
from creativeos_db.storyboard_service import StoryboardService
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.director import CampaignBrief, DeterministicMockCreativeDirectorProvider
from creativeos_db.director_service import CreativeDirectorService

class StoryboardUnitTests(unittest.TestCase):
    def test_validation_rollup_and_versions(self):
        with self.assertRaises(ValueError): validate_scene({"title":"","duration_seconds":1,"position":1})
        with self.assertRaises(ValueError): validate_scene({"title":"x","duration_seconds":1,"position":1,"scene_type":"REAL_UI","immutable_ui":True,"generation_method":"GENERATIVE"})
        r=rollup([{"duration_seconds":5,"cost_estimate_low_cents":10,"cost_estimate_high_cents":20,"status":"READY","approval_state":"APPROVED"}])
        self.assertEqual((r["duration_seconds"],r["estimated_low_cents"],r["approved_count"]),(5,10,1))
        self.assertEqual(next_version_number([{"version_number":1},{"version_number":3}]),4)

class StoryboardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Path(self.tmp.name)/"db.sqlite3"
        self.store=CreativeOSStore(self.db); self.assertEqual(self.store.migrate_to_latest(),12)
        self.brand=BrandBrainService(self.store).load_fleetpilot_fixture()
        self.campaign=self.store.create("campaigns",{"brand_profile_id":self.brand["id"],"title":"Launch"})
        brief=CampaignBrief(self.brand["id"],"Create explainer",self.brand["audience"],"aware",["fragmented workflow"],"fleet control","See demo","60s Explainer",60,"16:9","English","confident","none",85,15,"balanced","balanced",["preserve UI"])
        ds=CreativeDirectorService(self.store,DeterministicMockCreativeDirectorProvider())
        plan=ds.generate_plan(self.campaign["id"],brief,self.brand); ds.approve_plan(plan["id"])
        mat=ds.materialize_storyboard(plan["id"],"FleetPilot Explainer")
        self.board=mat["storyboard"]; self.service=StoryboardService(self.store)
    def tearDown(self):
        self.store.close(); self.tmp.cleanup()
    def test_operations_versions_and_safety(self):
        scenes=self.service.list_scenes(self.board["id"]); self.assertEqual(len(scenes),8)
        real=next(s for s in scenes if s["scene_type"]=="REAL_UI")
        self.assertEqual(real["generation_method"],"COMPOSITING_ONLY"); self.assertEqual(real["immutable_ui"],1)
        self.service.set_approval(real["id"],True); self.service.set_lock(real["id"],True)
        with self.assertRaises(ValueError): self.service.update_scene(real["id"],{"title":"bad"})
        v1=self.service.create_version(real["id"],"COMPOSITING",prompt="pan and callout")
        v2=self.service.create_version(real["id"],"COMPOSITING",prompt="zoom")
        self.assertEqual((v1["version_number"],v2["version_number"]),(1,2))
        self.service.approve_version(v1["id"])
        self.assertEqual(self.store.get("scene_versions",v1["id"])["is_approved"],1)
        scene_after=self.store.get("scenes",real["id"])
        self.assertEqual(scene_after["selected_version_id"],v2["id"])
        self.assertEqual(scene_after["approved_version_id"],v1["id"])
        ids=[s["id"] for s in scenes][::-1]; reordered=self.service.reorder(self.board["id"],ids)
        self.assertEqual([s["id"] for s in reordered],ids)
        dup=self.service.duplicate_scene(scenes[0]["id"]); self.assertTrue(dup["title"].endswith("Copy"))
        totals=self.service.rollup(self.board["id"]); self.assertGreater(totals["duration_seconds"],0)

    def test_restart_persistence_and_migration(self):
        scene=self.service.list_scenes(self.board["id"])[0]
        self.service.set_lock(scene["id"],True)
        v=self.service.create_version(scene["id"],"EDIT",prompt="version A")
        sid=scene["id"]; vid=v["id"]; self.store.close()
        self.store=CreativeOSStore(self.db); self.service=StoryboardService(self.store)
        self.assertEqual(self.store.schema_version(),12)
        self.assertEqual(self.store.get("scenes",sid)["locked"],1)
        self.assertEqual(self.store.get("scene_versions",vid)["version_number"],1)
        self.assertEqual(self.store.get("scenes",sid)["selected_version_id"],vid)

    def test_v3_v4_rollback_reapply_preserves_prior_data(self):
        self.assertEqual(self.store.rollback_to(3),3)
        self.assertEqual(self.store.get("brand_profiles",self.brand["id"])["name"],"FleetPilot")
        self.assertEqual(len(self.store.list("director_plans")),1)
        self.assertEqual(self.store.migrate_to_latest(),12)

if __name__=="__main__": unittest.main()
