import json
from pathlib import Path

import pytest

from cryptoquant.cli import main, begin_step, finish_step

CONFIG = Path(__file__).parents[1] / "configs/first_experiment.toml"


def test_no_account_or_live_commands_exist():
    with pytest.raises(SystemExit):
        main(["live"])


def test_invalid_experiment_cannot_escape_output_root(tmp_path):
    with pytest.raises(ValueError):
        begin_step(tmp_path, "../escape", "prepare", "hash")


def test_new_pipeline_completion_and_duplicate_steps(tmp_path):
    experiment, attempt = begin_step(tmp_path, "EXP-001", "prepare", "hash")
    assert attempt.name == "attempt-001"
    finish_step(experiment, "prepare", "complete", {"manifest": "file"})
    with pytest.raises(ValueError, match="completed"):
        begin_step(tmp_path, "EXP-001", "prepare", "hash")
    _, second = begin_step(tmp_path, "EXP-001", "rules", "hash")
    assert second.exists()
    finish_step(experiment, "rules", "complete", {})
    begin_step(tmp_path, "EXP-001", "check-data", "hash")
    with pytest.raises(ValueError, match="config"):
        begin_step(tmp_path, "EXP-001", "rules", "different")


def test_failed_step_requires_explicit_resume_preserving_logs(tmp_path):
    experiment, attempt = begin_step(tmp_path, "EXP-001", "prepare", "hash")
    (attempt / "error.txt").write_text("failure")
    finish_step(experiment, "prepare", "failed", {"error": "offline"})
    with pytest.raises(ValueError, match="resume"):
        begin_step(tmp_path, "EXP-001", "prepare", "hash")
    _, retried = begin_step(tmp_path, "EXP-001", "prepare", "hash", resume=True)
    assert retried.name == "attempt-002"
    assert (attempt / "error.txt").read_text() == "failure"


def test_later_step_requires_completed_dependencies(tmp_path):
    with pytest.raises(ValueError):
        begin_step(tmp_path, "EXP-001", "rules", "hash")
    experiment, _ = begin_step(tmp_path, "EXP-001", "prepare", "hash")
    with pytest.raises(ValueError):
        begin_step(tmp_path, "EXP-001", "check-data", "hash")


def test_existing_unrecognized_experiment_directory_is_not_overwritten(tmp_path):
    folder = tmp_path / "EXP-001"
    folder.mkdir()
    (folder / "old.json").write_text("important")
    with pytest.raises(ValueError):
        begin_step(tmp_path, "EXP-001", "prepare", "hash")


def test_state_write_interruption_does_not_leave_unrecoverable_attempt(tmp_path, monkeypatch):
    import cryptoquant.cli as cli
    original = cli.write_json
    def disk_error(*args, **kwargs):
        raise OSError("disk write interrupted")
    monkeypatch.setattr(cli, "write_json", disk_error)
    with pytest.raises(OSError):
        begin_step(tmp_path, "EXP-001", "prepare", "hash")
    monkeypatch.setattr(cli, "write_json", original)
    _, retried = begin_step(tmp_path, "EXP-001", "prepare", "hash", resume=True)
    assert retried.is_dir()


def test_interrupted_atomic_state_publish_is_resumed(tmp_path, monkeypatch):
    import cryptoquant.cli as cli
    original = cli.os.replace
    monkeypatch.setattr(cli.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("publish interrupted")))
    with pytest.raises(OSError):
        begin_step(tmp_path, "EXP-001", "prepare", "hash")
    assert (tmp_path / "EXP-001/step_state.json.tmp").is_file()
    monkeypatch.setattr(cli.os, "replace", original)
    _, retried = begin_step(tmp_path, "EXP-001", "prepare", "hash", resume=True)
    assert retried.name == "attempt-002"
    assert (tmp_path / "EXP-001/step_state.json").is_file()


def test_foreign_temporary_state_is_never_adopted(tmp_path):
    folder = tmp_path / "EXP-001"
    folder.mkdir()
    (folder / "step_state.json.tmp").write_text(json.dumps({"experiment_id": "EXP-999", "config_hash": "hash", "type": "data_check", "steps": {}}))
    with pytest.raises(ValueError):
        begin_step(tmp_path, "EXP-001", "prepare", "hash", resume=True)
    assert (folder / "step_state.json.tmp").exists()
