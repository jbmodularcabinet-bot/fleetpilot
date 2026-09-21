import unittest

from creativeos_db import Asset, BrandProfile, Campaign, ExportJob, GenerationJob, QAResult, Scene, Storyboard


class DomainEntityTests(unittest.TestCase):
    def test_all_v1_entities_construct(self) -> None:
        brand = BrandProfile("b1", "Brand")
        campaign = Campaign("c1", brand.id, "Campaign")
        board = Storyboard("s1", campaign.id, "Board")
        scene = Scene("sc1", board.id, "Hook", 1)
        asset = Asset("a1", "screenshot", "ui.png", True)
        job = GenerationJob("g1", scene.id, "mock", "video", "DRAFT")
        qa = QAResult("q1", campaign.id, "resolution", "PASS")
        export = ExportJob("e1", campaign.id, "16:9", "DRAFT")
        self.assertEqual(
            [type(x).__name__ for x in (brand, campaign, board, scene, asset, job, qa, export)],
            ["BrandProfile", "Campaign", "Storyboard", "Scene", "Asset", "GenerationJob", "QAResult", "ExportJob"],
        )


if __name__ == "__main__":
    unittest.main()
