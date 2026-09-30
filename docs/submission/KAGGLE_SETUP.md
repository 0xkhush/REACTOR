# Kaggle overnight evaluation

The private audio-only dataset is [zxkhush/reactor-fdb-v3-audio](https://www.kaggle.com/datasets/zxkhush/reactor-fdb-v3-audio). It contains 100 released `input.wav` recordings, a SHA-256 manifest, attribution and license metadata. The upload excludes scenario answers and API keys.

The private T4 [GPU ASR check](https://www.kaggle.com/code/zxkhush/reactor-gpu-asr-check) passed on Python 3.12.13, PyTorch 2.10.0+cu128 and Tesla T4: the pinned `nvidia/parakeet-tdt-0.6b-v2` model transcribed one recording. `gpu_probe_report.json` is available from that notebook's Output tab.

The private [overnight FDB-v3 notebook](https://www.kaggle.com/code/zxkhush/reactor-overnight-fdb-v3-evaluation) is prepared. Versions 1 and 2 completed without inference because the four Kaggle Secrets had not been granted. Their saved `reactor-run-manifest.json` files report an error before any model call. A new notebook version must be pushed after the Secrets are enabled.

## One user action before the full run

Open the overnight notebook in Kaggle, choose **Add-ons → Secrets**, create or select these exact labels, and enable notebook access for each:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `GOOGLE_API_KEY`

Use the matching LiveKit URL/key/secret from the same LiveKit project and the confirmed Free-tier Google AI Studio key. Never put values in notebook source, Kaggle dataset metadata, Git, screenshots, or chat. Granting notebook access is a Kaggle UI action; the CLI cannot create these secrets.

Once enabled, the agent will push a new version of the overnight script with Kaggle GPU enabled. The run clones pinned REACTOR/FDB revisions into ephemeral `/kaggle/temp`, reads the four secrets at runtime, and removes its temporary `.env.local` during shutdown. It copies the audio into `/kaggle/working/fdb_v3_data_released`, streams recordings through the LiveKit agent, transcribes input/output with Parakeet, and writes:

- `reactor-run-manifest.json` — completion count, failures and model/provenance (no secrets).
- `tool_accuracy_exact.json`, `strict_pass_exact.json` — local exact-match evaluation **without** the paid semantic judge.
- Per-example WAV and result JSON files; the batch may produce large Kaggle outputs.

The script continues on Kaggle after the browser/chat closes. A Kaggle `COMPLETE` status alone does not mean a valid benchmark run: inspect its saved manifest. Resource quota, rate limits and service faults can still interrupt it. The inference notebook still requires four Secrets; it did not run the submitted capture batch.

## Actual evaluation path: Mac capture + secret-free Kaggle ASR

The actual completed evaluation used `scripts/batch_infer.py` on the Mac and `remote_eval/asr_eval/run_asr_eval.py` on Kaggle's T4. Input recordings and generated results were private datasets. The ASR-only job needs **no** API Secrets and no hosted model calls. Its reports, transcripts and call records are archived in `docs/results/FDB_v3_exact_reports.zip`.

The captured batch had 100 attempts: 37 with tools and 63 without, no final transport failure. The strict local exact report is **12/100**, with judge disabled. Capture spanned pre-release configurations; it is not a clean full run of the final reviewed candidate. Audio-timeline latency equivalence is unverified. See `docs/results/README.md` for these limits.

Download only the published files; temporary clones/audio are removed before publishing output to reduce Kaggle output pagination:

```bash
.venv/bin/kaggle kernels output zxkhush/reactor-fdb-v3-asr-evaluation \
  --file-pattern '(run_manifest|strict_pass_exact|tool_accuracy_exact|captured_results)\.(json|jsonl)$' \
  --page-size 200 -p artifacts/kaggle-corrected-reports
```

For the independent, Secrets-based overnight runner, the corresponding commands are:

```bash
.venv/bin/kaggle kernels status zxkhush/reactor-overnight-fdb-v3-evaluation
.venv/bin/kaggle kernels files zxkhush/reactor-overnight-fdb-v3-evaluation --page-size 20
.venv/bin/kaggle kernels output zxkhush/reactor-overnight-fdb-v3-evaluation \
  --file-pattern 'reactor-run-manifest.json|.*_exact.json' \
  -p artifacts/kaggle-overnight-results
```

The notebook is private. The requested official semantic-judge re-run is performed by the organizers; the local exact-match figures are diagnostic and can differ on equivalent arguments such as `2026-07-15` and `July 15`.
