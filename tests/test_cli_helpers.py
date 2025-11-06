import pydmp.cli as cli


def test_fmt_ddmmyy_valid_and_invalid():
    assert cli._fmt_ddmmyy("010125") == "01 Jan 2025"
    assert cli._fmt_ddmmyy("000000") == ""
    assert cli._fmt_ddmmyy(None) == ""  # type: ignore[arg-type]
    assert cli._fmt_ddmmyy("bad") == ""


def test_normalize_config_shapes(tmp_path):
    # panel mapping
    raw = {"panel": {"host": "h", "account": "1", "remote_key": "k", "port": "", "timeout": 5}}
    cfg = cli._normalize_config(raw)
    assert isinstance(cfg, dict) and "panel" in cfg
    assert cfg["panel"]["port"] > 0

    # top-level mapping
    raw2 = {"host": "h", "account": "1", "remote_key": "k"}
    cfg2 = cli._normalize_config(raw2)
    assert isinstance(cfg2, dict) and cfg2["panel"]["host"] == "h"

    # list shape
    raw3 = [raw2]
    cfg3 = cli._normalize_config(raw3)
    assert isinstance(cfg3, dict) and cfg3["panel"]["account"] == "1"
