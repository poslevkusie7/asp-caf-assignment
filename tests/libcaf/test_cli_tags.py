from libcaf.repository import Repository
from pytest import CaptureFixture

from caf import cli_commands


def _make_commit(temp_repo: Repository) -> str:
    f = temp_repo.working_dir / "file.txt"
    f.write_text("content")
    return temp_repo.commit_working_dir("Author", "msg")


def test_create_and_list_tags(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    commit_hash = _make_commit(temp_repo)

    assert cli_commands.create_tag(
        working_dir_path=temp_repo.working_dir,
        tag_name="v1.0",
        commit=commit_hash,
    ) == 0

    assert cli_commands.tags(working_dir_path=temp_repo.working_dir) == 0
    out = capsys.readouterr().out
    assert "v1.0" in out


def test_delete_tag_command(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    commit_hash = _make_commit(temp_repo)
    cli_commands.create_tag(
        working_dir_path=temp_repo.working_dir,
        tag_name="v1.0",
        commit=commit_hash,
    )

    assert cli_commands.delete_tag(
        working_dir_path=temp_repo.working_dir,
        tag_name="v1.0",
    ) == 0

    assert cli_commands.tags(working_dir_path=temp_repo.working_dir) == 0
    out = capsys.readouterr().out
    assert "No tags found" in out
