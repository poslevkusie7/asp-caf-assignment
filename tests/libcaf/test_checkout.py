from pathlib import Path

import pytest

from libcaf.repository import Repository
from libcaf.checkout import CheckoutError


def test_checkout_restores_file_content(temp_repo: Repository) -> None:
    f = temp_repo.working_dir / "a.txt"

    f.write_text("v1")
    commit1 = temp_repo.commit_working_dir("Author", "commit v1")

    f.write_text("v2")
    commit2 = temp_repo.commit_working_dir("Author", "commit v2")

    assert f.read_text() == "v2"

    temp_repo.checkout(str(commit1))

    assert f.read_text() == "v1"


def test_checkout_refuses_overwriting_dirty_modified_file(temp_repo: Repository) -> None:
    f = temp_repo.working_dir / "a.txt"

    f.write_text("v1")
    commit1 = temp_repo.commit_working_dir("Author", "commit v1")

    f.write_text("v2")
    temp_repo.commit_working_dir("Author", "commit v2")

    # Dirty local change on top of HEAD
    f.write_text("DIRTY LOCAL CHANGE")

    with pytest.raises(CheckoutError):
        temp_repo.checkout(str(commit1))


def test_checkout_refuses_overwriting_untracked_file_on_add(temp_repo: Repository) -> None:
    # commit1: empty (or at least does not include b.txt)
    (temp_repo.working_dir / "a.txt").write_text("base")
    commit1 = temp_repo.commit_working_dir("Author", "base")

    # commit2: adds b.txt
    b = temp_repo.working_dir / "b.txt"
    b.write_text("from commit2")
    commit2 = temp_repo.commit_working_dir("Author", "add b")

    # go back to commit1 so b.txt is removed
    temp_repo.checkout(str(commit1))
    assert not b.exists()

    # create an untracked b.txt that would conflict with checkout
    b.write_text("LOCAL UNTRACKED CONTENT")

    with pytest.raises(CheckoutError):
        temp_repo.checkout(str(commit2))


def test_checkout_handles_simple_rename_as_move(temp_repo: Repository) -> None:
    a = temp_repo.working_dir / "a.txt"
    b = temp_repo.working_dir / "b.txt"

    a.write_text("same-content")
    commit1 = temp_repo.commit_working_dir("Author", "has a")

    # "rename" a -> b with identical content (should be treated as move by diff)
    b.write_text(a.read_text())
    a.unlink()
    commit2 = temp_repo.commit_working_dir("Author", "rename to b")

    assert b.exists()
    assert not a.exists()

    # checkout back restores a and removes b
    temp_repo.checkout(str(commit1))
    assert a.exists()
    assert a.read_text() == "same-content"
    assert not b.exists()

    # checkout forward restores b and removes a
    temp_repo.checkout(str(commit2))
    assert b.exists()
    assert b.read_text() == "same-content"
    assert not a.exists()