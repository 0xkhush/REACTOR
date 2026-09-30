"""Render a 3–5 minute edited replay of actual captured voice/tool evidence.

This is not a screen recording or a live single take. Narration is synthesized;
the benchmark and kitchen sections use unmodified capture audio timelines.
Requires macOS say, ffmpeg/ffprobe, and Pillow. Does not call a hosted API.
"""

import json
import math
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "artifacts" / "demo-render"
OUTPUT = ROOT / "docs" / "submission" / "REACTOR_Demo_Replay.mp4"
FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")


def run(command):
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)


def duration(path):
    result = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                      "-of", "json", str(path)], text=True)
    return float(json.loads(result)["format"]["duration"])


def card(title, lines, note, path, *, fraction=0, trace_lines=()):
    image = Image.new("RGB", (1280, 720), (15, 23, 42))
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(str(FONT), 42)
    body_font = ImageFont.truetype(str(FONT), 25)
    small_font = ImageFont.truetype(str(FONT), 18)
    draw.text((65, 34), "REACTOR  /  THEME 05", fill=(125, 211, 252), font=small_font)
    draw.text((65, 80), title, fill=(242, 247, 255), font=title_font)
    y = 158
    for line in lines:
        for wrapped in textwrap.wrap(line, width=80):
            draw.text((65, y), wrapped, fill=(226, 232, 240), font=body_font)
            y += 33
        y += 12
    for line in trace_lines:
        draw.text((65, y), line[:95], fill=(134, 239, 172), font=small_font)
        y += 29
    draw.rectangle((65, 641, 1215, 647), fill=(51, 65, 85))
    draw.rectangle((65, 641, 65 + int(1150 * min(1, fraction)), 647), fill=(56, 189, 248))
    draw.text((65, 669), note[:125], fill=(148, 163, 184), font=small_font)
    image.save(path)


def narration(text, prefix):
    aiff, wav = WORK / f"{prefix}.aiff", WORK / f"{prefix}.wav"
    run(["say", "-v", "Samantha", "-r", "160", "-o", str(aiff), text])
    run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(wav)])
    return wav


def mix_capture(user, agent, prefix):
    wav = WORK / f"{prefix}.wav"
    # Keep original timing; voices are presented on separate stereo channels.
    graph = ("[0:a]aformat=channel_layouts=mono,aresample=48000,"
             "pan=stereo|c0=c0|c1=0*c0[u];"
             "[1:a]aformat=channel_layouts=mono,aresample=48000,"
             "pan=stereo|c0=0*c0|c1=c0[a];"
             "[u][a]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[out]")
    run(["ffmpeg", "-y", "-i", str(user), "-i", str(agent), "-filter_complex", graph,
         "-map", "[out]", "-c:a", "pcm_s16le", str(wav)])
    return wav


def segment(index, title, lines, note, audio, minimum_seconds=0, events=()):
    seconds = max(minimum_seconds, math.ceil(duration(audio)))
    frames = WORK / f"frames-{index}"
    frames.mkdir(exist_ok=True)
    for second in range(seconds + 1):
        visible = [f"TRACE +{when:05.1f}s  {text}" for when, text in events if second >= when]
        card(title, lines, note, frames / f"{second:04d}.png",
             fraction=second / max(1, seconds), trace_lines=visible)
    video = WORK / f"segment-{index}.mp4"
    run(["ffmpeg", "-y", "-framerate", "1", "-i", str(frames / "%04d.png"), "-i", str(audio),
         "-af", "apad", "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "27",
         "-pix_fmt", "yuv420p", "-r", "24", "-c:a", "aac", "-b:a", "128k", str(video)])
    return video


def build():
    if not FONT.is_file():
        raise RuntimeError("This local renderer requires macOS Arial and the say command")
    WORK.mkdir(parents=True, exist_ok=True)
    videos = []
    intro = narration(
        "This is REACTOR, an interruptible voice agent prototype for Theme Five. "
        "This video is an edited replay of actual captured sessions, with synthesized narration. "
        "You will hear a human benchmark recording and the agent's captured answer, followed by a "
        "synthetic kitchen timer test. We show the recorded tool evidence and our measured limitations, "
        "not a live single take or an official benchmark score.", "intro")
    videos.append(segment(1, "Interruptible voice-agent prototype", [
        "LiveKit + Gemini 2.5 Flash Native Audio",
        "Recorded sessions replayed with their actual tool-call evidence",
        "Edited replay: synthesized narration; no new model calls during rendering",
        "Source: github.com/0xkhush/REACTOR",
    ], "Edited evidence replay, not a live single take", intro, 29))

    architecture = narration(
        "The session controller tracks user-intent revisions, preserves unaffected slots, validates "
        "tool arguments, and coalesces duplicate proposals. Independent reads run asynchronously and "
        "writes are serialized. If intent changes, obsolete pending work is cancelled. A dispatched "
        "write remains in the ledger because cancelling an await does not undo a side effect.", "architecture")
    videos.append(segment(2, "One session owner, concurrent work", [
        "Speech -> LiveKit/Gemini -> turn bridge -> session controller",
        "Schema validation + request revisions + operation ledger",
        "Independent reads overlap; writes pass a serialized dispatch gate",
        "Late stale read results are withheld; completed writes stay recorded",
    ], "Controller guarantees are bounded; external rollback is not claimed", architecture, 24))

    folder = "ecommerce_19_66f59c766e7e22e1f90d08f6"
    result = json.loads((ROOT / "artifacts/batch_inference" / folder / "result.json").read_text())
    trace = [(call["timestamp_start"] - result["stream_start_time"],
              f"{call['function']}({json.dumps(call['args'], separators=(',', ':'))})")
             for call in result["actual_tool_calls"]]
    audio = mix_capture(ROOT / "fdb_v3_data_released" / folder / "input.wav",
                        ROOT / "artifacts/batch_inference" / folder / "output.wav", "benchmark")
    videos.append(segment(3, "FDB-v3: product + quantity self-correction", [
        "Human input recording (left) + captured agent output (right)",
        "Recorded chain: search_products -> returned product ID -> add_to_cart",
        "This example passes the local strict exact tool/argument check.",
        "Source: NTU Full-Duplex-Bench v3; CC BY-NC 4.0",
    ], "Trace clock is from the captured tool log; not a new execution", audio, events=trace))

    audio = mix_capture(ROOT / "artifacts/kitchen-smoke/conversation.wav",
                        ROOT / "artifacts/kitchen-smoke/reactor-kitchen-b5d2c20cb46b-agent.wav", "kitchen")
    videos.append(segment(4, "Extension: corrected kitchen timer + cancellation", [
        "Synthesized user: ten minutes -> actually seven minutes",
        "Kitchen-only final-transcript router; same versioned controller",
        "Follow-up: cancel pasta timer; returned ID used for cancellation",
        "Actual room: reactor-kitchen-b5d2c20cb46b",
    ], "Synthetic-speech integration smoke; not spontaneous human interruption", audio,
       events=[(33.9, "create_timer(name=pasta, duration_seconds=420)"),
               (43.1, "list_timers() -> timer-1"), (43.1, "cancel_timer(timer_id=timer-1)")]))

    results_audio = narration(
        "The captured batch attempted all one hundred recordings. Thirty seven generated tool calls; "
        "sixty three did not. The pinned local exact checker passed twelve out of one hundred strict "
        "tool and argument checks. This is a weak baseline, not a competitive result or an official "
        "normalized score. No paid semantic judge was used. Later prompt and argument-alias changes "
        "passed targeted tests but have not been evaluated on a new full batch.", "results")
    videos.append(segment(5, "Results, without hiding failures", [
        "100 captured attempts: 37 with tools / 63 without / 0 capture failures",
        "Pinned local exact checker: 25/100 tool selection; 12/100 strict pass",
        "No semantic judge: these are not official normalized scores",
        "Latest candidate has targeted checks only; full batch predates it",
    ], "No qualification or performance improvement is claimed", results_audio, 30))

    final_audio = narration(
        "To reproduce, supply your own credentials in the ignored local environment file and "
        "download the released audio. The repository pins the voice SDK and upstream benchmark. "
        "The Mac batch captures audio and tool logs; Kaggle's free T four runs Parakeet transcription "
        "and exact scoring. Our next priorities are reliable tool selection, better acoustic turn "
        "handling, and an independent full run of the final configuration.", "reproduction")
    videos.append(segment(6, "Reproduction and next steps", [
        "bash scripts/reproduce.sh --check  (no hosted inference)",
        "Mac capture: scripts/batch_infer.py  |  GPU: remote_eval/asr_eval",
        "Credentials excluded; benchmark labels read only by evaluator",
        "github.com/0xkhush/REACTOR  |  docs/submission for setup and reports",
    ], "Team details and final hosting link must be added before submission", final_audio, 26))
    concat = WORK / "segments.txt"
    concat.write_text("".join(f"file '{video}'\n" for video in videos))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c", "copy", "-movflags", "+faststart", str(OUTPUT)])
    length = duration(OUTPUT)
    if not 180 <= length <= 300:
        raise RuntimeError(f"Replay duration outside requested 3–5 minutes: {length}")
    print(json.dumps({"file": str(OUTPUT), "seconds": round(length, 2),
                      "edited_replay": True, "new_hosted_calls": 0}))


if __name__ == "__main__":
    build()
