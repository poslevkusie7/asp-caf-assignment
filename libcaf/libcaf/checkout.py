from pathlib import Path
from collections.abc import Callable, Generator, Sequence

from . import TreeRecordType
from .diff import AddedDiff, Diff, ModifiedDiff, MovedFromDiff, MovedToDiff, RemovedDiff
from .plumbing import hash_file, load_tree, load_commit, open_content_for_reading
from .ref import HashRef, write_ref

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .repository import Repository

class CheckoutError(Exception):
    """Exception raised for checkout-related errors."""
    
def checkout(repo: "Repository", target_commit: "HashRef") -> None:
    """Update working directory to match the target commit. #?

    :param repo: The repository instance.
    :param target_commit: The target commit hash to checkout.
    :raises CheckoutError: If local changes would be overwritten."""
    head_commit = repo.head_commit()
    if head_commit is None:
        checkout_from_empty(repo, target_commit)
        write_ref(repo.head_file(), target_commit)
        return
    
    diffs = repo.diff(head_commit, target_commit)
    validate_clean(repo, diffs, repo.working_dir)
    apply_checkout(repo, diffs, repo.working_dir)
    write_ref(repo.head_file(), target_commit)
    
def checkout_from_empty(repo: "Repository", target_commit: HashRef) -> None:
    commit = load_commit(repo.objects_dir(), target_commit)
    target_tree = load_tree(repo.objects_dir(), commit.tree_hash)

    validate_new_tree(repo, commit.tree_hash, repo.working_dir)

    create_tree(repo, commit.tree_hash, repo.working_dir)
    
    
def validate_clean(repo: "Repository", diffs: Sequence[Diff], current_path: Path) -> None:
    """Recursively validate that checking out will not overwrite dirty files."""
    for diff in diffs:
        path = current_path / diff.record.name
        
        # If it's a directory structure change that isn't a simple add/remove blob
        if diff.record.type == TreeRecordType.TREE:
            if isinstance(diff, (AddedDiff, MovedFromDiff)):
                # Ensure we aren't overwriting untracked files with a new directory structure
                validate_new_tree(repo, diff.record.hash, path)
            elif isinstance(diff, (RemovedDiff, MovedToDiff)):
                # Ensure we aren't deleting a directory that has dirty files
                validate_removed_tree(repo, diff.record.hash, path)
            else:
                validate_clean(repo, diff.children, path)
            continue

        # Handle Files (Blobs)
        if isinstance(diff, (ModifiedDiff, RemovedDiff, MovedToDiff)):
            if not path.exists():
                # File missing but expected by HEAD is technically a modification (deletion).
                # Git usually errors here if it needs to change the file.
                msg = f"Your local changes to the following files would be overwritten by checkout:\n\t{path}"
                raise CheckoutError(msg)

            if hash_file(path) != diff.record.hash:
                msg = f"Your local changes to the following files would be overwritten by checkout:\n\t{path}"
                raise CheckoutError(msg)

        if isinstance(diff, (AddedDiff, MovedFromDiff)):
            if path.exists():
                # Check for untracked file collision
                # If the untracked file matches the new content, it's fine.
                target_hash = diff.record.hash 
                if hash_file(path) != target_hash:
                    msg = f"Untracked working tree file '{path}' would be overwritten by checkout."
                    raise CheckoutError(msg)


def validate_new_tree(repo: "Repository", tree_hash: str, path: Path) -> None:
    """Validate that adding a new tree won't overwrite untracked files."""
    tree = load_tree(repo.objects_dir(), tree_hash)
    for name, record in tree.records.items():
        child_path = path / name
        if record.type == TreeRecordType.TREE:
            validate_new_tree(repo, record.hash, child_path)
        elif child_path.exists():
            if hash_file(child_path) != record.hash:
                msg = f"Untracked working tree file '{child_path}' would be overwritten by checkout."
                raise CheckoutError(msg)


def validate_removed_tree(repo: "Repository", tree_hash: str, path: Path) -> None:
    """Validate that removing a tree won't lose dirty files."""
    if not path.exists():
        return
        
    tree = load_tree(repo.objects_dir(), tree_hash)
    for name, record in tree.records.items():
        child_path = path / name
        if record.type == TreeRecordType.TREE:
            validate_removed_tree(repo, record.hash, child_path)
        elif child_path.exists() and hash_file(child_path) != record.hash:
            msg = f"Your local changes to the following files would be overwritten by checkout:\n\t{child_path}"
            raise CheckoutError(msg)


def apply_checkout(repo: "Repository", diffs: Sequence[Diff], current_path: Path) -> None:
    """Recursively apply changes to the working directory."""
    for diff in diffs:
        path = current_path / diff.record.name

        if isinstance(diff, RemovedDiff):
            if diff.record.type == TreeRecordType.TREE:
                delete_tree(path)
            else:
                if path.exists():
                    path.unlink()
            continue

        if isinstance(diff, MovedToDiff):
            # The source of a move is effectively a removal
            if diff.record.type == TreeRecordType.TREE:
                delete_tree(path)
            elif path.exists():
                path.unlink()
            continue

        if diff.record.type == TreeRecordType.TREE:
            if isinstance(diff, AddedDiff):
                path.mkdir(exist_ok=True)
                create_tree(repo, diff.record.hash, path)
            else:
                path.mkdir(exist_ok=True)
                apply_checkout(repo, diff.children, path)
            continue
            
        # Blob Operations (Added, Modified, MovedFrom)
        target_hash = None
        if isinstance(diff, ModifiedDiff):
            target_hash = diff.new_record.hash
        elif isinstance(diff, (AddedDiff, MovedFromDiff)):
            target_hash = diff.record.hash
            
        if target_hash:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open_content_for_reading(repo.objects_dir(), target_hash) as src:
                with path.open("wb") as dst:
                    dst.write(src.read())


def create_tree(repo: "Repository", tree_hash: str, path: Path) -> None:
    """Recursively create a full directory tree."""
    tree = load_tree(repo.objects_dir(), tree_hash)
    for name, record in tree.records.items():
        child_path = path / name
        if record.type == TreeRecordType.TREE:
            child_path.mkdir(exist_ok=True)
            create_tree(repo, record.hash, child_path)
        else:
            with open_content_for_reading(repo.objects_dir(), record.hash) as src:
                with child_path.open("wb") as dst:
                    dst.write(src.read())


def delete_tree(path: Path) -> None:
    """Recursively delete a directory locally."""
    if not path.exists():
        return
    for item in path.iterdir():
        if item.is_dir():
            delete_tree(item)
        else:
            item.unlink()
    path.rmdir()
    