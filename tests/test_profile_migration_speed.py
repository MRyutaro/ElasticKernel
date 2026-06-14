"""Tests for profile_migration_speed.

D-11 (first half): the function previously shelled out via
os.system("rm -rf {} && mkdir {}"), which breaks (or worse) when the notebook
directory path contains spaces or shell metacharacters. It now uses
shutil.rmtree + os.makedirs, so a path with a space must work cleanly.
"""

from pathlib import Path

from elastic_notebook.core.common.profile_migration_speed import (
    profile_migration_speed,
)


def test_handles_directory_with_space(tmp_path):
    spaced_dir = tmp_path / "dir with space"
    spaced_dir.mkdir()

    result = profile_migration_speed(str(spaced_dir))

    # Returns a numeric speed and does not raise on the spaced path.
    assert isinstance(result, float)
    # The scratch directory is cleaned up afterwards.
    assert not (spaced_dir / "measure_speed").exists()


def test_creates_and_cleans_scratch_dir(tmp_path):
    result = profile_migration_speed(str(tmp_path))
    assert isinstance(result, float)
    assert not (Path(tmp_path) / "measure_speed").exists()
