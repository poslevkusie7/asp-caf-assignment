from pathlib import Path

from libcaf.repository import Repository, RepositoryError
from pytest import raises


def test_tags_initially_empty(temp_repo: Repository) -> None:
    assert temp_repo.tags() == []


def _make_commit(temp_repo: Repository) -> str:
    f = temp_repo.working_dir / "file.txt"
    f.write_text("content")
    return temp_repo.commit_working_dir("Author", "msg")


def test_create_tag_success_and_list(temp_repo: Repository) -> None:
    commit_hash = _make_commit(temp_repo)

    temp_repo.create_tag("v1.0", commit_hash)

    # tag appears in tags()
    assert "v1.0" in temp_repo.tags()

    # tag file contains the commit hash
    tag_path = temp_repo.tags_dir() / "v1.0"
    assert tag_path.exists()
    assert tag_path.read_text().strip() == commit_hash


def test_create_tag_existing_name_raises_repository_error(temp_repo: Repository) -> None:
    commit_hash = _make_commit(temp_repo)
    temp_repo.create_tag("v1.0", commit_hash)

    with raises(RepositoryError, match='Tag "v1.0" already exists'):
        temp_repo.create_tag("v1.0", commit_hash)


def test_create_tag_empty_name_raises_value_error(temp_repo: Repository) -> None:
    commit_hash = _make_commit(temp_repo)

    with raises(ValueError, match="Tag name is required"):
        temp_repo.create_tag("", commit_hash)


def test_delete_tag_success(temp_repo: Repository) -> None:
    commit_hash = _make_commit(temp_repo)
    temp_repo.create_tag("v1.0", commit_hash)

    temp_repo.delete_tag("v1.0")

    assert "v1.0" not in temp_repo.tags()
    assert not (temp_repo.tags_dir() / "v1.0").exists()


def test_delete_nonexistent_tag_raises_repository_error(temp_repo: Repository) -> None:
    with raises(RepositoryError, match='Tag "nope" does not exist.'):
        temp_repo.delete_tag("nope")
