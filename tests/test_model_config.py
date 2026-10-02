import pytest

from app import config


@pytest.mark.parametrize("mode", ["test", "final"])
def test_model_selection(monkeypatch, mode):
    monkeypatch.setattr(config, "MODEL_MODE", mode)
    monkeypatch.setattr(config, "TEST_MODEL_ID", "test-model")
    monkeypatch.setattr(config, "FINAL_EXTRACTION_MODEL_ID", "final-extraction")
    monkeypatch.setattr(config, "FINAL_AGENT_MODEL_ID", "final-agent")
    assert config.get_extraction_model_id() == (
        "test-model" if mode == "test" else "final-extraction"
    )
    assert config.get_agent_model_id() == (
        "test-model" if mode == "test" else "final-agent"
    )


@pytest.mark.parametrize("getter", [config.get_extraction_model_id, config.get_agent_model_id])
def test_invalid_mode(monkeypatch, getter):
    monkeypatch.setattr(config, "MODEL_MODE", "typo")
    with pytest.raises(ValueError, match="MODEL_MODE"):
        getter()


@pytest.mark.parametrize("mode,setting,getter", [
    ("test", "TEST_MODEL_ID", config.get_extraction_model_id),
    ("test", "TEST_MODEL_ID", config.get_agent_model_id),
    ("final", "FINAL_EXTRACTION_MODEL_ID", config.get_extraction_model_id),
    ("final", "FINAL_AGENT_MODEL_ID", config.get_agent_model_id),
])
def test_missing_selected_model(monkeypatch, mode, setting, getter):
    monkeypatch.setattr(config, "MODEL_MODE", mode)
    monkeypatch.setattr(config, setting, "")
    with pytest.raises(ValueError, match=setting):
        getter()
