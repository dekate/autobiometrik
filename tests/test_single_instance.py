import sys

import pytest

from autobiometrik import single_instance


def test_acquire_true_off_windows():
    if sys.platform == "win32":
        pytest.skip("covered by the Windows-specific test")
    assert single_instance.acquire("autobiometrik-test-nonwin") is True


def test_second_acquire_same_name_fails_on_windows():
    if sys.platform != "win32":
        pytest.skip("named mutex is Windows-only")
    name = "autobiometrik-bpjs-test-guard-A1"
    assert single_instance.acquire(name) is True
    assert single_instance.acquire(name) is False
