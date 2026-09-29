import json
import asyncio
import sys
import time
from pathlib import Path

import pytest

from scripts.smoke_fdb import check_dataset, matching_calls, count_completed, managed_worker, require_ffmpeg, check_livekit_credentials
from reactor.config import AgentConfig, ConfigurationError


def test_dataset_check_uses_audio_paths_not_answer_metadata(tmp_path):
    folder = tmp_path / "travel_01_speaker"
    folder.mkdir()
    (folder / "input.wav").write_bytes(b"RIFF")
    (folder / "metadata.json").write_text("this is not parsed")
    assert check_dataset(tmp_path) == [folder / "input.wav"]


def test_empty_dataset_is_a_failure(tmp_path):
    with pytest.raises(ValueError, match="no input.wav"):
        check_dataset(tmp_path)


def test_only_requested_room_tool_calls_are_counted(tmp_path):
    log = tmp_path / "tools.jsonl"
    log.write_text("\n".join(json.dumps({"room": room, "call": {"function": name}})
                             for room, name in [("a", "search_flights"), ("b", "book_flight"),
                                                ("a", "book_flight")]))
    assert matching_calls(log, "a") == ["search_flights", "book_flight"]


def test_full_coverage_does_not_count_failed_result_as_completed(tmp_path):
    for index, status in enumerate(["completed", "inference_failed"]):
        folder = tmp_path / f"sample_{index}"
        folder.mkdir()
        (folder / "result_gemini2_5.json").write_text(json.dumps({"status": status}))
    assert count_completed(tmp_path, "gemini2_5") == (1, 1)


def test_managed_worker_terminates_its_child_even_when_smoke_fails():
    with pytest.raises(RuntimeError, match="smoke failed"):
        with managed_worker([sys.executable, "-c", "import time; time.sleep(20)"], startup_seconds=0.05) as proc:
            assert proc.poll() is None
            raise RuntimeError("smoke failed")
    assert proc.poll() is not None


def test_smoke_checks_ffmpeg_before_starting_worker(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        require_ffmpeg()


def test_livekit_401_is_reported_without_exposing_credentials():
    class Rejected(Exception):
        status = 401

    class Room:
        async def list_rooms(self, request):
            raise Rejected("contains-secret-value")

    class Client:
        room = Room()
        closed = False

        async def aclose(self):
            self.closed = True

    client = Client()
    config = AgentConfig("wss://example.livekit.cloud", "key", "contains-secret-value", "google", "model")
    with pytest.raises(ConfigurationError, match="LiveKit project URL and API key/secret") as error:
        asyncio.run(check_livekit_credentials(config, factory=lambda **kwargs: client))
    assert "contains-secret-value" not in str(error.value)
    assert client.closed
