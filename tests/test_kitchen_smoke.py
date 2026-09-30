import wave

from scripts.kitchen_smoke import join_wav_turns


def test_kitchen_wav_keeps_both_turns_separated_by_silence(tmp_path):
    first, second = tmp_path / "first.wav", tmp_path / "second.wav"
    for path, payload in [(first, b"\x01\x00" * 480), (second, b"\x02\x00" * 960)]:
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            wav.writeframes(payload)
    output = tmp_path / "conversation.wav"
    join_wav_turns(first, second, output, pause_seconds=1, trailing_seconds=2)
    with wave.open(str(output), "rb") as wav:
        assert wav.getframerate() == 48000
        assert wav.getnframes() == 480 + 48000 + 960 + 96000
        samples = wav.readframes(wav.getnframes())
        assert samples[:960] == b"\x01\x00" * 480
        assert samples[960:960 + 48000 * 2] == b"\x00" * 48000 * 2


def test_kitchen_wav_can_leave_a_lead_in_for_livekit_join(tmp_path):
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b"\x01\x00" * 480)
    output = tmp_path / "joined.wav"
    join_wav_turns(source, source, output, pause_seconds=0, trailing_seconds=0, lead_seconds=1)
    with wave.open(str(output), "rb") as wav:
        result = wav.readframes(wav.getnframes())
    assert result[:96000] == b"\x00" * 96000
    assert result[96000:96960] == b"\x01\x00" * 480
