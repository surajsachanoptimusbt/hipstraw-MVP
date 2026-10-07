"""T010: Unit tests for config loading (contracts/config.md)."""

from pathlib import Path

import pytest
import yaml

from hipstraw_mm.config import (
    load_config,
    load_first_position,
    load_metro_config,
    load_program_config,
    load_run_config,
    load_source_policy,
)
from hipstraw_mm.errors import ConfigError

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
POSITIONS_DIR = Path(__file__).resolve().parents[2] / "positions"
KNOWN_INTERESTS = {"invoice_accuracy_entitlement", "scope_drift_prevention"}


def _mutated(tmp_path: Path, source: Path, mutate) -> Path:
    """Copy a shipped YAML file to tmp_path after applying `mutate` to its parsed content."""
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    mutate(data)
    out = tmp_path / source.name
    out.write_text(yaml.safe_dump(data), encoding="utf-8")
    return out


class TestProgramConfig:
    PATH = CONFIG_DIR / "programs" / "invoice_alpha.yaml"

    def test_loads_invoice_alpha(self):
        cfg = load_program_config(self.PATH)
        assert cfg.programId == "invoice_alpha_genesis"
        assert len(cfg.experimentContexts) == 6
        assert len(cfg.primaryInterests) == 6

    def test_five_experiment_contexts_rejected(self, tmp_path):
        path = _mutated(tmp_path, self.PATH, lambda d: d["experimentContexts"].pop())
        with pytest.raises(ConfigError):
            load_program_config(path)

    def test_seven_primary_interests_rejected(self, tmp_path):
        path = _mutated(tmp_path, self.PATH, lambda d: d["primaryInterests"].append({"id": "extra", "label": "Extra"}))
        with pytest.raises(ConfigError):
            load_program_config(path)


class TestRunConfig:
    PATH = CONFIG_DIR / "run.yaml"

    def test_loads(self):
        cfg = load_run_config(self.PATH)
        assert cfg.projectId.startswith("demo-")
        assert cfg.budgets.companiesKept <= 10
        assert cfg.budgets.profileHopsPerRun > 0

    def test_non_demo_project_rejected(self, tmp_path):
        path = _mutated(tmp_path, self.PATH, lambda d: d.update(projectId="hipstraw-prod"))
        with pytest.raises(ConfigError):
            load_run_config(path)

    def test_companies_kept_over_10_rejected(self, tmp_path):
        path = _mutated(tmp_path, self.PATH, lambda d: d["budgets"].update(companiesKept=11))
        with pytest.raises(ConfigError):
            load_run_config(path)

    def test_missing_profile_hops_rejected(self, tmp_path):
        path = _mutated(tmp_path, self.PATH, lambda d: d["budgets"].pop("profileHopsPerRun"))
        with pytest.raises(ConfigError):
            load_run_config(path)

    def test_model_name_resolves_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "gpt-4o-test")
        cfg = load_run_config(self.PATH)
        assert cfg.model.name == "gpt-4o-test"

    def test_model_name_is_none_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        cfg = load_run_config(self.PATH)
        assert cfg.model.name is None


class TestSourcePolicy:
    PATH = CONFIG_DIR / "source_policy.yaml"

    def test_loads(self):
        cfg = load_source_policy(self.PATH)
        assert "linkedin.com" in cfg.denylistDomains
        assert set(cfg.reliabilityWeights) == {"high", "medium", "low"}
        assert set(cfg.sourceTypeDomains) <= {"registry", "job_board", "directory", "news"}

    def test_missing_weight_key_rejected(self, tmp_path):
        path = _mutated(tmp_path, self.PATH, lambda d: d["reliabilityWeights"].pop("low"))
        with pytest.raises(ConfigError):
            load_source_policy(path)

    def test_extra_weight_key_rejected(self, tmp_path):
        path = _mutated(tmp_path, self.PATH, lambda d: d["reliabilityWeights"].update(top=1.0))
        with pytest.raises(ConfigError):
            load_source_policy(path)

    @pytest.mark.parametrize("bad", [0, -0.1, 1.5])
    def test_weight_out_of_range_rejected(self, tmp_path, bad):
        path = _mutated(tmp_path, self.PATH, lambda d: d["reliabilityWeights"].update(medium=bad))
        with pytest.raises(ConfigError):
            load_source_policy(path)

    def test_unknown_source_type_category_rejected(self, tmp_path):
        path = _mutated(tmp_path, self.PATH, lambda d: d["sourceTypeDomains"].update(blog=["x.test"]))
        with pytest.raises(ConfigError):
            load_source_policy(path)


class TestMetroConfig:
    def test_loads(self):
        cfg = load_metro_config(CONFIG_DIR / "metros.yaml")
        assert {m.id for m in cfg.metros} == {"atlanta", "san_francisco", "new_york"}

    def test_silicon_valley_cities_in_san_francisco(self):
        cfg = load_metro_config(CONFIG_DIR / "metros.yaml")
        sf = next(m for m in cfg.metros if m.id == "san_francisco")
        for city in [
            "San Jose",
            "Palo Alto",
            "Mountain View",
            "Sunnyvale",
            "Santa Clara",
            "Menlo Park",
            "Redwood City",
        ]:
            assert city in sf.places

    def test_run_metro_ids_must_exist(self, tmp_path):
        for name in ["metros.yaml", "source_policy.yaml"]:
            (tmp_path / name).write_text((CONFIG_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
        _mutated(tmp_path, CONFIG_DIR / "run.yaml", lambda d: d["constraints"].update(metroIds=["boston"]))
        with pytest.raises(ConfigError):
            load_config(tmp_path)


class TestFirstPosition:
    PATH = POSITIONS_DIR / "first_position.example.yaml"

    def test_loads_example(self):
        pos = load_first_position(self.PATH, known_interest_ids=KNOWN_INTERESTS)
        assert pos.candidateId == "invoice_alpha_genesis__saas_recurring_fees"
        assert pos.searchHints == ["optional keyword"]

    @pytest.mark.parametrize(
        "field", ["candidateId", "segment", "companyArchetype", "buyer", "problem", "trigger", "primaryInterestIds"]
    )
    def test_required_field_missing_rejected(self, tmp_path, field):
        path = _mutated(tmp_path, self.PATH, lambda d: d.pop(field))
        with pytest.raises(ConfigError):
            load_first_position(path, known_interest_ids=KNOWN_INTERESTS)

    def test_search_hints_optional(self, tmp_path):
        path = _mutated(tmp_path, self.PATH, lambda d: d.pop("searchHints"))
        pos = load_first_position(path, known_interest_ids=KNOWN_INTERESTS)
        assert pos.searchHints == []

    def test_empty_primary_interests_rejected(self, tmp_path):
        path = _mutated(tmp_path, self.PATH, lambda d: d.update(primaryInterestIds=[]))
        with pytest.raises(ConfigError):
            load_first_position(path, known_interest_ids=KNOWN_INTERESTS)

    def test_unknown_primary_interest_rejected(self):
        with pytest.raises(ConfigError):
            load_first_position(self.PATH, known_interest_ids={"some_other_interest"})
