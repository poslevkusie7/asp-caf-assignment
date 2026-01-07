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
    
def test_checkout_refuses_overwriting_untracked_file_in_new_dir(temp_repo: Repository) -> None:
    # commit1: does NOT contain dir/
    (temp_repo.working_dir / "base.txt").write_text("base")
    commit1 = temp_repo.commit_working_dir("Author", "base")

    # commit2: adds dir/inside.txt
    d = temp_repo.working_dir / "dir"
    d.mkdir()
    inside = d / "inside.txt"
    inside.write_text("from commit2")
    commit2 = temp_repo.commit_working_dir("Author", "add dir with file")

    # Go back to commit1 => dir removed
    temp_repo.checkout(str(commit1))
    assert not d.exists()

    # Create local untracked dir/file that will conflict
    d.mkdir()
    inside.write_text("LOCAL UNTRACKED CONTENT")

    with pytest.raises(CheckoutError):
        temp_repo.checkout(str(commit2))

def test_checkout_refuses_removing_dir_with_dirty_file(temp_repo: Repository) -> None:
    d = temp_repo.working_dir / "dir"
    d.mkdir()
    f = d / "file.txt"
    f.write_text("v1")
    commit1 = temp_repo.commit_working_dir("Author", "add dir/file")

    # commit2 removes the directory
    f.unlink()
    d.rmdir()
    commit2 = temp_repo.commit_working_dir("Author", "remove dir")

    # Go back to commit1, then make local dirty edit
    temp_repo.checkout(str(commit1))
    f.write_text("DIRTY LOCAL CHANGE")

    with pytest.raises(CheckoutError):
        temp_repo.checkout(str(commit2))
        
def test_checkout_removes_deleted_tracked_file(temp_repo: Repository) -> None:
    x = temp_repo.working_dir / "x.txt"

    x.write_text("keep then delete")
    commit1 = temp_repo.commit_working_dir("Author", "add x")

    x.unlink()
    commit2 = temp_repo.commit_working_dir("Author", "delete x")

    # Ensure we are at commit2 state
    assert not x.exists()

    # Go back to commit1 => x appears
    temp_repo.checkout(str(commit1))
    assert x.exists()
    assert x.read_text() == "keep then delete"

    # Go to commit2 => x removed
    temp_repo.checkout(str(commit2))
    assert not x.exists()