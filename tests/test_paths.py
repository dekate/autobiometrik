from pathlib import Path

from autobiometrik import paths


def test_base_dir_is_cwd_when_not_frozen():
    assert paths.base_dir() == Path.cwd()


def test_resource_path_points_into_package_when_not_frozen():
    p = paths.resource_path("icon.png")
    assert p.name == "icon.png"
    assert p.parent.name == "autobiometrik"
    assert p.exists()  # icon.png already ships in the package


def test_log_path_is_autobiometrik_log_in_base_dir():
    assert paths.log_path() == paths.base_dir() / "autobiometrik.log"
