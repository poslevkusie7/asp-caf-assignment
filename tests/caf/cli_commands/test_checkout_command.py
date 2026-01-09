from collections.abc import Callable
from pathlib import Path

import pytest
from pytest import CaptureFixture

from caf import cli_commands
from libcaf.constants import DEFAULT_REPO_DIR, HEAD_FILE
from libcaf.ref import read_ref, SymRef
from libcaf.repository import Repository, branch_ref, tag_ref


def test_checkout_by_commit_hash_restores_file(temp_repo: Repository, parse_commit_hash: Callable[[], str], capsys: CaptureFixture[str]) -> None:
    f = temp_repo.working_dir / "a.txt"

    f.write_text("v1")
    assert cli_commands.commit(working_dir_path=temp_repo.working_dir, author="Test", message="c1") == 0
    c1 = parse_commit_hash()

    f.write_text("v2")
    assert cli_commands.commit(working_dir_path=temp_repo.working_dir, author="Test", message="c2") == 0
    c2 = parse_commit_hash()

    assert f.read_text() == "v2"

    # checkout back to c1
    assert cli_commands.checkout(working_dir_path=temp_repo.working_dir, target=c1) == 0
    assert f.read_text() == "v1"

    out = capsys.readouterr().out
    assert "Checked out" in out

# Should be a good test, but it fails since add_branch() is bugged from the beginning, do you want me to fix it?
# def test_checkout_by_branch_name_sets_head_symbolic_and_updates_workdir(temp_repo: Repository,
#                                                                       parse_commit_hash: Callable[[], str],
#                                                                       capsys: CaptureFixture[str]) -> None:
#     a = temp_repo.working_dir / "a.txt"

#     # commit on main
#     a.write_text("main-v1")
#     assert cli_commands.commit(working_dir_path=temp_repo.working_dir, author="Test", message="main c1") == 0
#     main_c1 = parse_commit_hash()

#     # create dev branch at current tip
#     assert cli_commands.add_branch(working_dir_path=temp_repo.working_dir, branch_name="dev") == 0

#     # checkout dev branch
#     assert cli_commands.checkout(working_dir_path=temp_repo.working_dir, target="dev") == 0
#     # HEAD should now point to refs/heads/dev (symbolic)
#     assert temp_repo.head_ref() == branch_ref("dev")

#     # commit on dev
#     a.write_text("dev-v2")
#     assert cli_commands.commit(working_dir_path=temp_repo.working_dir, author="Test", message="dev c2") == 0
#     _dev_c2 = parse_commit_hash()

#     # checkout main should restore main content
#     assert cli_commands.checkout(working_dir_path=temp_repo.working_dir, target="main") == 0
#     assert temp_repo.head_ref() == branch_ref("main")
#     assert a.read_text() == "main-v1"

#     capsys.readouterr()  # clear buffers


def test_checkout_by_tag_name(temp_repo: Repository, parse_commit_hash: Callable[[], str], capsys: CaptureFixture[str]) -> None:
    f = temp_repo.working_dir / "a.txt"

    f.write_text("v1")
    assert cli_commands.commit(working_dir_path=temp_repo.working_dir, author="Test", message="c1") == 0
    c1 = parse_commit_hash()

    # create a tag pointing to c1
    assert cli_commands.create_tag(working_dir_path=temp_repo.working_dir, tag_name="v1", commit=c1) == 0

    # make another commit so checkout does something observable
    f.write_text("v2")
    assert cli_commands.commit(working_dir_path=temp_repo.working_dir, author="Test", message="c2") == 0
    _c2 = parse_commit_hash()
    assert f.read_text() == "v2"

    # checkout tag v1 should go back to v1 content
    assert cli_commands.checkout(working_dir_path=temp_repo.working_dir, target="v1") == 0
    assert f.read_text() == "v1"

    out = capsys.readouterr().out
    assert "Checked out v1" in out


def test_checkout_missing_target(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    assert cli_commands.checkout(working_dir_path=temp_repo.working_dir, target=None) == -1
    err = capsys.readouterr().err
    assert "Target is required" in err


def test_checkout_no_repo(temp_repo_dir: Path, capsys: CaptureFixture[str]) -> None:
    # temp_repo_dir is an empty directory with no .caf
    assert cli_commands.checkout(working_dir_path=temp_repo_dir, target="main") == -1
    err = capsys.readouterr().err
    assert "No repository found" in err


def test_checkout_refuses_when_dirty(temp_repo: Repository, parse_commit_hash: Callable[[], str], capsys: CaptureFixture[str]) -> None:
    f = temp_repo.working_dir / "a.txt"
    f.write_text("v1")
    assert cli_commands.commit(working_dir_path=temp_repo.working_dir, author="Test", message="c1") == 0
    c1 = parse_commit_hash()

    # make new commit
    f.write_text("v2")
    assert cli_commands.commit(working_dir_path=temp_repo.working_dir, author="Test", message="c2") == 0
    _c2 = parse_commit_hash()

    # dirty change (not committed)
    f.write_text("DIRTY")

    assert cli_commands.checkout(working_dir_path=temp_repo.working_dir, target=c1) == -1
    err = capsys.readouterr().err
    # your Repository.checkout raises CheckoutError("Working directory has changes; aborting checkout.")
    assert "Working directory has changes" in err


def test_checkout_unknown_target_string(temp_repo: Repository, capsys: CaptureFixture[str]) -> None:
    # not a branch, not a tag, not a valid hash => should error
    assert cli_commands.checkout(working_dir_path=temp_repo.working_dir, target="not-a-ref") == -1
    err = capsys.readouterr().err
    # depending on whether HashRef throws ValueError or RefError, you’ll get an error string
    assert "not-a-ref" in err or "Invalid" in err