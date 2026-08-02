from app_update_checker import is_newer_version, version_tuple


def test_version_tuple_accepts_release_tags():
    assert version_tuple("v1.2.3") == (1, 2, 3)


def test_newer_version_comparison():
    assert is_newer_version("1.0.1", "1.0.0")
    assert is_newer_version("1.1.0", "1.0.9")
    assert not is_newer_version("1.0.0", "1.0.0")
    assert not is_newer_version("0.9.9", "1.0.0")
