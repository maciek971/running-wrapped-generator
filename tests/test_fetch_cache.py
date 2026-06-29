from pathlib import Path

from fetch_garmin import _resolve_cache_dir

HERE = Path("/proj")


def test_env_var_wins():
    assert _resolve_cache_dir("/env/cache", {"cache_dir": "/cfg/cache"}, HERE) == Path("/env/cache")


def test_me_json_cache_dir_used_when_no_env():
    # this is the bug that bit the deploy: generate honors cache_dir, so fetch must too
    assert _resolve_cache_dir(None, {"cache_dir": "/cfg/cache"}, HERE) == Path("/cfg/cache")


def test_defaults_to_here_cache():
    assert _resolve_cache_dir(None, {}, HERE) == Path("/proj/cache")
    assert _resolve_cache_dir(None, None, HERE) == Path("/proj/cache")


def test_empty_env_string_ignored():
    assert _resolve_cache_dir("", {"cache_dir": "/cfg/cache"}, HERE) == Path("/cfg/cache")
