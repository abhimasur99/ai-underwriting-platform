"""CLI: runs sample deals end to end offline."""
from bridge.cli import main

from tests.conftest import DEALS_DIR


def run(tmp_path, *args):
    return main([*map(str, args), "--db", str(tmp_path / "t.db"), "--quiet"])


def test_runs_a_deal_offline_and_prints_events(tmp_path, capsys):
    assert run(tmp_path, DEALS_DIR / "bronx_mf") == 0
    out = capsys.readouterr().out
    assert "chief -> extraction: extract_deal" in out
    assert "call: SCREEN" in out and "checker: pass" in out
    assert (tmp_path / "outputs" / "D-0042" / "v1" / "memo.pdf").exists()
    assert (tmp_path / "outputs" / "D-0042" / "v1" / "workbook.xlsx").exists()


def test_all_three_deals_run_end_to_end(tmp_path, capsys):
    assert run(tmp_path, DEALS_DIR / "bronx_mf", DEALS_DIR / "queens_mixed_use",
               DEALS_DIR / "overleveraged_bk") == 0
    out = capsys.readouterr().out
    for call in ("SCREEN", "WATCH", "DECLINE"):
        assert f"call: {call}" in out
    assert out.count("checker: pass") == 3


def test_forced_mismatch_once_retries_then_passes(tmp_path, capsys):
    assert run(tmp_path, DEALS_DIR / "bronx_mf", "--force-mismatch") == 0
    out = capsys.readouterr().out
    assert "check.retry" in out and "retries: 1" in out and "escalated: False" in out


def test_forced_mismatch_persisting_escalates(tmp_path, capsys):
    assert run(tmp_path, DEALS_DIR / "bronx_mf", "--force-mismatch", "persist") == 0
    out = capsys.readouterr().out
    assert out.count("check.retry") == 2 and "retries: 2" in out and "escalated: True" in out
    assert "checker: fail" in out


def test_rerunning_uses_a_new_deal_id(tmp_path, capsys):
    run(tmp_path, DEALS_DIR / "bronx_mf")
    run(tmp_path, DEALS_DIR / "bronx_mf")
    assert "as D-0002" in capsys.readouterr().out


def test_fresh_starts_over(tmp_path, capsys):
    run(tmp_path, DEALS_DIR / "bronx_mf")
    run(tmp_path, DEALS_DIR / "bronx_mf", "--fresh")
    assert capsys.readouterr().out.count("as D-0042") == 2


def test_an_incomplete_folder_is_reported_not_crashed(tmp_path, capsys):
    import shutil
    d = tmp_path / "bad"
    shutil.copytree(DEALS_DIR / "bronx_mf", d)
    shutil.rmtree(d / "cached")
    (d / "t12.csv").unlink()
    assert run(tmp_path, d) == 1
    assert "not ready: still missing t12" in capsys.readouterr().out


def test_a_missing_field_is_reported_not_crashed(tmp_path, capsys):
    import shutil
    d = tmp_path / "bad"
    shutil.copytree(DEALS_DIR / "bronx_mf", d)
    shutil.rmtree(d / "cached")
    p = d / "deal_summary.md"
    p.write_text(p.read_text().replace("- Note rate: 10.50% interest-only\n", ""))
    assert run(tmp_path, d) == 1
    assert "not ready" in capsys.readouterr().out


def test_live_without_a_key_stops_cleanly(tmp_path, monkeypatch):
    import pytest
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("bridge.settings.load_dotenv", lambda *a, **k: None)
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, DEALS_DIR / "bronx_mf", "--live")
    assert "ANTHROPIC_API_KEY" in str(exc.value)
