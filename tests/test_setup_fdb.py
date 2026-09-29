from pathlib import Path

import pytest

from scripts.setup_fdb import REVISION, setup


def test_existing_upstream_checkout_is_pinned():
    path = Path("vendor/Full-Duplex-Bench")
    if not path.exists():
        pytest.skip("Pinned upstream checkout is not present")
    assert REVISION == "3e799c45a045256f47d5f1c9cda90157e2d2ec9e"
    assert (setup(path) / "mock_apis.py").is_file()


def test_does_not_create_destination_with_missing_parent(tmp_path):
    with pytest.raises(FileNotFoundError):
        setup(tmp_path / "missing" / "checkout")
