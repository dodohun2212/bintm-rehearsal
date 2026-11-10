import config


def test_config_basic():
    assert config.LLM_MODEL
    assert config.DIAG_MIN_PCT == 20
    assert config.ESSAY_MIN_PCT == 50
