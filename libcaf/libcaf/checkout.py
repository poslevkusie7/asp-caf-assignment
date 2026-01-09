from pathlib import Path
from collections.abc import Callable, Generator, Sequence
import shutil

from . import TreeRecordType
from .diff import AddedDiff, Diff, ModifiedDiff, MovedFromDiff, MovedToDiff, RemovedDiff
from .plumbing import hash_file, load_tree, load_commit, open_content_for_reading

class CheckoutError(Exception):
    """Exception raised for checkout-related errors."""

def apply_checkout(objects_dir: Path, diffs: Sequence[Diff], current_path: Path) -> None:
    """Apply changes to the working directory."""
    stack: list[tuple[Sequence[Diff], Path]] = [(diffs, current_path)]

    while stack:
        cur_diffs, cur_path = stack.pop()

        for diff in cur_diffs:
            path = cur_path / diff.record.name

            if isinstance(diff, (RemovedDiff, MovedToDiff)):
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                continue
            
            if isinstance(diff, (AddedDiff, MovedFromDiff)):
                if diff.record.type == TreeRecordType.TREE:
                    create_tree(objects_dir, diff.record.hash, path)
                else:
                    write_blob(objects_dir, diff.record.hash, path)
                continue

            if isinstance(diff, ModifiedDiff):
                if diff.record.type == TreeRecordType.TREE:
                    path.mkdir(parents=True, exist_ok=True)
                    stack.append((diff.children, path))
                    
                else:
                    if diff.new_record is None:
                        raise CheckoutError(f"Invalid modified diff for {path}: missing new_record")
                    write_blob(objects_dir, diff.new_record.hash, path)
                continue

            raise CheckoutError(f"Unhandled diff type: {type(diff).__name__} for {path}")

def create_tree(objects_dir: Path, tree_hash: str, path: Path) -> None:
    """Recursively create a full directory tree."""
    stack: list[tuple[str, Path]] = [(tree_hash, path)]
    while stack:
        cur_tree_hash, cur_path = stack.pop()
        cur_path.mkdir(parents=True, exist_ok=True)
        
        tree = load_tree(objects_dir, cur_tree_hash)
        for name, record in tree.records.items():
            child_path = cur_path / name
            if record.type == TreeRecordType.TREE:
                stack.append((record.hash, child_path))
            else:
                write_blob(objects_dir, record.hash, child_path)

def write_blob(objects_dir: Path, blob_hash: str, dst_path: Path) -> None:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with open_content_for_reading(objects_dir, blob_hash) as src:
        with dst_path.open("wb") as dst:
            shutil.copyfileobj(src, dst)
            