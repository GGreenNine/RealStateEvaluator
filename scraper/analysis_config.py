from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - import guard for missing optional install state
    yaml = None


@dataclass(frozen=True, slots=True)
class OpenAIAnalysisConfig:
    model: str
    temperature: float
    max_output_tokens: int
    timeout_seconds: int
    retries: int
    prompt_path: Path


@dataclass(frozen=True, slots=True)
class PathsAnalysisConfig:
    run_input_glob: str
    scored_dir_name: str
    llm_payload_dir_name: str
    leaderboard_csv_name: str
    leaderboard_json_name: str


@dataclass(frozen=True, slots=True)
class FiltersAnalysisConfig:
    min_rooms: int
    reject_parse_error: bool
    skip_if_already_scored: bool
    min_hard_score_for_llm: float


@dataclass(frozen=True, slots=True)
class RoomGateConfig:
    enabled: bool
    min_rooms: int
    fail_score: float
    disqualify_below_min_rooms: bool
    unknown_rooms_action: str


@dataclass(frozen=True, slots=True)
class ScoreAnchorConfig:
    value: float
    points: float


@dataclass(frozen=True, slots=True)
class BuildingAgeConfig:
    anchors: tuple[ScoreAnchorConfig, ...]


@dataclass(frozen=True, slots=True)
class PlotOwnershipConfig:
    owned_points: float
    leased_points: float
    unknown_points: float


@dataclass(frozen=True, slots=True)
class PricePerM2Config:
    anchors: tuple[ScoreAnchorConfig, ...]


@dataclass(frozen=True, slots=True)
class SizeConfig:
    anchors: tuple[ScoreAnchorConfig, ...]
    below_min_points: float


@dataclass(frozen=True, slots=True)
class FloorConfig:
    first_floor_points: float
    other_floors_points: float
    unknown_floor_points: float


@dataclass(frozen=True, slots=True)
class MaintenanceFeeConfig:
    best_fee_per_m2: float
    worst_fee_per_m2: float
    max_points: float
    min_points: float


@dataclass(frozen=True, slots=True)
class TransitConfig:
    strong_score_threshold: float
    multimodal_bonus: float


@dataclass(frozen=True, slots=True)
class HardScoringConfig:
    room_gate: RoomGateConfig
    building_age: BuildingAgeConfig
    plot_ownership: PlotOwnershipConfig
    price_per_m2: PricePerM2Config
    size: SizeConfig
    maintenance_fee: MaintenanceFeeConfig
    transit: TransitConfig
    floor: FloorConfig


@dataclass(frozen=True, slots=True)
class ScoreRangeConfig:
    min_points: float
    max_points: float


@dataclass(frozen=True, slots=True)
class ConfidenceConfig:
    min_allowed: float
    warn_below: float


@dataclass(frozen=True, slots=True)
class LLMScoringConfig:
    renovations: ScoreRangeConfig
    confidence: ConfidenceConfig


@dataclass(frozen=True, slots=True)
class LLMInputConfig:
    preserve_full_text: bool


@dataclass(frozen=True, slots=True)
class OutputConfig:
    primary_leaderboard_format: str
    also_write_json: bool
    include_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MetadataConfig:
    save_input_hash: bool
    save_prompt_version: bool
    save_model_name: bool


@dataclass(frozen=True, slots=True)
class ApartmentAnalysisConfig:
    version: int
    project_root: Path
    openai: OpenAIAnalysisConfig
    paths: PathsAnalysisConfig
    filters: FiltersAnalysisConfig
    hard_scoring: HardScoringConfig
    llm_scoring: LLMScoringConfig
    llm_input: LLMInputConfig
    output: OutputConfig
    metadata: MetadataConfig

    @property
    def prompt_version(self) -> str:
        return f"{self.openai.prompt_path.stem}_v{self.version}"


def _resolve_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (project_root / path).resolve()


def _load_score_anchors(values: list[dict]) -> tuple[ScoreAnchorConfig, ...]:
    anchors: list[ScoreAnchorConfig] = []
    for item in values:
        anchors.append(
            ScoreAnchorConfig(
                value=float(item["value"]),
                points=float(item["points"]),
            )
        )
    return tuple(sorted(anchors, key=lambda anchor: anchor.value))


def load_apartment_analysis_config(
    path: Path | str = Path("config/apartment_analysis.yaml"),
) -> ApartmentAnalysisConfig:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is not installed. Run `pip install -r requirements.txt` "
            "or `pip install PyYAML` in the active virtual environment."
        )
    config_path = Path(path).resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = config_path.parent.parent

    openai_raw = raw["openai"]
    paths_raw = raw["paths"]
    filters_raw = raw["filters"]
    hard_raw = raw["hard_scoring"]
    llm_raw = raw["llm_scoring"]
    llm_input_raw = raw["llm_input"]
    output_raw = raw["output"]
    metadata_raw = raw["metadata"]

    return ApartmentAnalysisConfig(
        version=int(raw["version"]),
        project_root=project_root,
        openai=OpenAIAnalysisConfig(
            model=str(openai_raw["model"]),
            temperature=float(openai_raw["temperature"]),
            max_output_tokens=int(openai_raw["max_output_tokens"]),
            timeout_seconds=int(openai_raw["timeout_seconds"]),
            retries=int(openai_raw["retries"]),
            prompt_path=_resolve_path(project_root, str(openai_raw["prompt_path"])),
        ),
        paths=PathsAnalysisConfig(
            run_input_glob=str(paths_raw["run_input_glob"]),
            scored_dir_name=str(paths_raw["scored_dir_name"]),
            llm_payload_dir_name=str(paths_raw["llm_payload_dir_name"]),
            leaderboard_csv_name=str(paths_raw["leaderboard_csv_name"]),
            leaderboard_json_name=str(paths_raw["leaderboard_json_name"]),
        ),
        filters=FiltersAnalysisConfig(
            min_rooms=int(filters_raw["min_rooms"]),
            reject_parse_error=bool(filters_raw["reject_parse_error"]),
            skip_if_already_scored=bool(filters_raw["skip_if_already_scored"]),
            min_hard_score_for_llm=float(filters_raw["min_hard_score_for_llm"]),
        ),
        hard_scoring=HardScoringConfig(
            room_gate=RoomGateConfig(
                enabled=bool(hard_raw["room_gate"]["enabled"]),
                min_rooms=int(hard_raw["room_gate"]["min_rooms"]),
                fail_score=float(hard_raw["room_gate"]["fail_score"]),
                disqualify_below_min_rooms=bool(
                    hard_raw["room_gate"]["disqualify_below_min_rooms"]
                ),
                unknown_rooms_action=str(hard_raw["room_gate"]["unknown_rooms_action"]),
            ),
            building_age=BuildingAgeConfig(
                anchors=_load_score_anchors(hard_raw["building_age"]["anchors"]),
            ),
            plot_ownership=PlotOwnershipConfig(
                owned_points=float(hard_raw["plot_ownership"]["owned_points"]),
                leased_points=float(hard_raw["plot_ownership"]["leased_points"]),
                unknown_points=float(hard_raw["plot_ownership"]["unknown_points"]),
            ),
            price_per_m2=PricePerM2Config(
                anchors=_load_score_anchors(hard_raw["price_per_m2"]["anchors"]),
            ),
            size=SizeConfig(
                anchors=_load_score_anchors(hard_raw["size"]["anchors"]),
                below_min_points=float(hard_raw["size"]["below_min_points"]),
            ),
            maintenance_fee=MaintenanceFeeConfig(
                best_fee_per_m2=float(hard_raw["maintenance_fee"]["best_fee_per_m2"]),
                worst_fee_per_m2=float(hard_raw["maintenance_fee"]["worst_fee_per_m2"]),
                max_points=float(hard_raw["maintenance_fee"]["max_points"]),
                min_points=float(hard_raw["maintenance_fee"]["min_points"]),
            ),
            transit=TransitConfig(
                strong_score_threshold=float(hard_raw["transit"]["strong_score_threshold"]),
                multimodal_bonus=float(hard_raw["transit"]["multimodal_bonus"]),
            ),
            floor=FloorConfig(
                first_floor_points=float(hard_raw["floor"]["first_floor_points"]),
                other_floors_points=float(hard_raw["floor"]["other_floors_points"]),
                unknown_floor_points=float(hard_raw["floor"]["unknown_floor_points"]),
            ),
        ),
        llm_scoring=LLMScoringConfig(
            renovations=ScoreRangeConfig(
                min_points=float(llm_raw["renovations"]["min_points"]),
                max_points=float(llm_raw["renovations"]["max_points"]),
            ),
            confidence=ConfidenceConfig(
                min_allowed=float(llm_raw["confidence"]["min_allowed"]),
                warn_below=float(llm_raw["confidence"]["warn_below"]),
            ),
        ),
        llm_input=LLMInputConfig(
            preserve_full_text=bool(llm_input_raw["preserve_full_text"]),
        ),
        output=OutputConfig(
            primary_leaderboard_format=str(output_raw["primary_leaderboard_format"]),
            also_write_json=bool(output_raw["also_write_json"]),
            include_columns=tuple(str(value) for value in output_raw["include_columns"]),
        ),
        metadata=MetadataConfig(
            save_input_hash=bool(metadata_raw["save_input_hash"]),
            save_prompt_version=bool(metadata_raw["save_prompt_version"]),
            save_model_name=bool(metadata_raw["save_model_name"]),
        ),
    )
