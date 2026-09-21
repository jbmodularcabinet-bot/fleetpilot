from dataclasses import dataclass


@dataclass(frozen=True)
class BrandProfile:
    id: str
    name: str
    display_name: str = ""
    description: str = ""
    industry: str = ""
    positioning: str = ""
    audience: str = ""
    tagline: str = ""
    default_immutable_ui: bool = False


@dataclass(frozen=True)
class Campaign:
    id: str
    brand_profile_id: str
    title: str


@dataclass(frozen=True)
class Storyboard:
    id: str
    campaign_id: str
    title: str


@dataclass(frozen=True)
class Scene:
    id: str
    storyboard_id: str
    title: str
    position: int

@dataclass(frozen=True)
class Asset:
    id: str
    asset_type: str
    path: str
    immutable_ui: bool


@dataclass(frozen=True)
class GenerationJob:
    id: str
    scene_id: str
    provider: str
    model: str
    state: str


@dataclass(frozen=True)
class QAResult:
    id: str
    campaign_id: str
    check_type: str
    status: str


@dataclass(frozen=True)
class ExportJob:
    id: str
    campaign_id: str
    preset: str
    state: str
