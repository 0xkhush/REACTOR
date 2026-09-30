from google.genai import types

from reactor.config import AgentConfig
from reactor.voice.agent import build_model


def config(mode):
    return AgentConfig("wss://example.livekit.cloud", "test-key", "test-secret", "test-google-key",
                       model="test-model", mode=mode, free_quota_confirmed=True)


def test_benchmark_model_emits_pause_tolerant_vad_config_while_preserving_barge_in(monkeypatch):
    # Replace only the external model constructor; inspect our emitted API config.
    monkeypatch.setattr("reactor.voice.agent.google.realtime.RealtimeModel", lambda **options: options)
    options = build_model(config("benchmark"))
    assert "realtime_input_config" in options
    incoming = options["realtime_input_config"]
    assert incoming.automatic_activity_detection.silence_duration_ms == 1000
    assert incoming.automatic_activity_detection.end_of_speech_sensitivity == types.EndSensitivity.END_SENSITIVITY_LOW
    assert incoming.activity_handling == types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS


def test_kitchen_model_retains_existing_provider_turn_timing(monkeypatch):
    monkeypatch.setattr("reactor.voice.agent.google.realtime.RealtimeModel", lambda **options: options)
    assert "realtime_input_config" not in build_model(config("kitchen"))
