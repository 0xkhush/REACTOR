"""Checkout a fixed upstream FDB-v3 revision into an ignored local directory."""

import argparse
import subprocess
from pathlib import Path


UPSTREAM = "https://github.com/DanielLin94144/Full-Duplex-Bench.git"
REVISION = "3e799c45a045256f47d5f1c9cda90157e2d2ec9e"


def download_dataset_if_missing(dataset_dir: Path) -> None:
    if dataset_dir.is_dir() and any(dataset_dir.glob("*/input.wav")):
        return
    import re
    import zipfile
    import requests
    file_id = "1SO_4MTazWQ_jvCx0dtmpQ-t40bdd07yz"
    session = requests.Session()
    resp = session.get(f"https://drive.google.com/uc?id={file_id}&export=download")
    uuid_match = re.search(r'name="uuid"\s+value="([^"]+)"', resp.text)
    uuid = uuid_match.group(1) if uuid_match else None
    download_url = "https://drive.usercontent.google.com/download"
    params = {"id": file_id, "export": "download", "confirm": "t"}
    if uuid:
        params["uuid"] = uuid
    zip_path = dataset_dir.parent / "fdb_v3_data_released.tmp.zip"
    with session.get(download_url, params=params, stream=True) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dataset_dir.parent)
    if zip_path.exists():
        zip_path.unlink()


def patch_upstream_evaluator(v3_dir: Path) -> None:
    eval_script = v3_dir / "evaluate_tool_calls.py"
    if not eval_script.is_file():
        return
    content = eval_script.read_text(encoding="utf-8")
    target = '    print(f"    Tool Selection Acc : {bm[\'tool_selection_acc\']:.1%}")'
    if target in content:
        replacement = (
            '    tool_sel_str = f"{bm[\'tool_selection_acc\']:.1%}" if bm[\'tool_selection_acc\'] is not None else "N/A"\n'
            '    arg_acc_str = f"{bm[\'argument_acc\']:.1%}" if bm[\'argument_acc\'] is not None else "N/A"\n'
            '    print(f"    Tool Selection Acc : {tool_sel_str}")\n'
            '    print(f"    Argument Acc       : {arg_acc_str}")'
        )
        content = content.replace(
            '    print(f"    Tool Selection Acc : {bm[\'tool_selection_acc\']:.1%}")\n'
            '    print(f"    Argument Acc       : {bm[\'argument_acc\']:.1%}")',
            replacement,
        )
        content = content.replace(
            'parts = [f"{m}={v:.1%}" for m, v in metrics.items()]',
            'parts = [f"{m}={v:.1%}" if v is not None else f"{m}=N/A" for m, v in metrics.items()]',
        )
        eval_script.write_text(content, encoding="utf-8")


def setup(destination: Path, *, with_data: bool = False) -> Path:
    destination = destination.resolve()
    if destination.exists():
        actual = subprocess.check_output(
            ["git", "-C", str(destination), "rev-parse", "HEAD"], text=True
        ).strip()
        if actual != REVISION:
            raise RuntimeError("Existing FDB checkout has a different commit; leave it untouched")
    else:
        if not destination.parent.is_dir():
            raise FileNotFoundError(f"Parent directory does not exist: {destination.parent}")
        subprocess.run(["git", "clone", "--filter=blob:none", UPSTREAM, str(destination)], check=True)
        subprocess.run(["git", "-C", str(destination), "checkout", "--detach", REVISION], check=True)
    patch_upstream_evaluator(destination / "v3")
    if with_data:
        download_dataset_if_missing(destination.parent.parent / "fdb_v3_data_released")
    return destination / "v3"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path("vendor/Full-Duplex-Bench"))
    parser.add_argument("--with-data", action="store_true", help="Download released benchmark dataset if missing")
    args = parser.parse_args()
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    print(setup(args.destination, with_data=args.with_data))

