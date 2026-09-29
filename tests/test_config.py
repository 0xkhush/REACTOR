import pytest

from reactor.config import AgentConfig, ConfigurationError, load_config


VALID = {
    "LIVEKIT_URL": "wss://example.livekit.cloud",
    "LIVEKIT_API_KEY": "local-test-key",
    "LIVEKIT_API_SECRET": "local-test-secret",
    "GOOGLE_API_KEY": "local-test-google",
    "GOOGLE_LIVE_MODEL": "gemini-2.5-flash-native-audio-preview-12-2025",
    "REACTOR_MODE": "benchmark",
}


@pytest.mark.parametrize("field,replacement", [
    ("LIVEKIT_URL", "wss://your-project.livekit.cloud"),
    ("LIVEKIT_URL", "http://example.livekit.cloud"),
    ("LIVEKIT_API_KEY", "replace-with-your-livekit-api-key"),
    ("LIVEKIT_API_SECRET", ""),
    ("GOOGLE_API_KEY", ""),
    ("GOOGLE_LIVE_MODEL", ""),
    ("REACTOR_MODE", "other"),
])
def test_rejects_missing_or_placeholder_config_without_leaking_values(field, replacement):
    values = {**VALID, field: replacement}
    with pytest.raises(ConfigurationError) as error:
        AgentConfig.from_values(values)
    assert replacement not in str(error.value) if replacement else True


def test_live_calls_require_explicit_free_quota_confirmation():
    config = AgentConfig.from_values(VALID)
    with pytest.raises(ConfigurationError, match="free quota"):
        config.require_live_access()
    confirmed = AgentConfig.from_values({**VALID, "REACTOR_FREE_QUOTA_CONFIRMED": "yes"})
    confirmed.require_live_access()
    assert "local-test-google" not in repr(confirmed)
    assert "local-test-secret" not in repr(confirmed)


def test_config_loader_does_not_mutate_process_environment(tmp_path, monkeypatch):
    file = tmp_path / ".env.local"
    file.write_text("\n".join(f"{key}={value}" for key, value in VALID.items()))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    config = load_config(file)
    assert config.mode == "benchmark"
    assert "GOOGLE_API_KEY" not in __import__("os").environ


def test_kitchen_mode_is_supported():
    assert AgentConfig.from_values({**VALID, "REACTOR_MODE": "kitchen"}).mode == "kitchen"


def test_local_nonsecret_run_settings_can_override_env_file(tmp_path, monkeypatch):
    file = tmp_path / ".env.local"
    file.write_text("\n".join(f"{key}={value}" for key, value in VALID.items()))
    monkeypatch.setenv("GOOGLE_LIVE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")
    monkeypatch.setenv("REACTOR_FREE_QUOTA_CONFIRMED", "yes")
    config = load_config(file)
    config.require_live_access()
    assert config.model == "gemini-2.5-flash-native-audio-preview-12-2025"
    assert config.google_key == "local-test-google"
