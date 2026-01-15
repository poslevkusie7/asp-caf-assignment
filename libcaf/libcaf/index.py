"""Index management functions for libcaf."""

import contextlib
import os
import time
import warnings
from pathlib import Path
from typing import IO, Iterator

from . import Tree, TreeRecord, TreeRecordType
from .plumbing import hash_object, save_file_content, save_tree


@contextlib.contextmanager
def index_lock_file(index_path: Path) -> Iterator[IO[str]]:
    """Context manager for locking the index file using busy-wait exclusive creation.

    :param index_path: The path to the index file to lock.
    :yield: A text file object open for writing the index.lock file.
    :raises TimeoutError: If the lock file cannot be created after repeated attempts.
    """
    lock_path = index_path.with_suffix('.lock')

    # Ensure the repository directory exists
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Configuration
    sleep_time = 0.01
    max_wait_seconds = 300  # 5 minutes
    start_monotonic = time.monotonic()

    while True:
        try:
            # Try to create the lock file exclusively
            lock_file = open(lock_path, 'x', encoding='utf-8')
            break
        except FileExistsError:
            # 1. Check for timeout
            elapsed = time.monotonic() - start_monotonic
            if elapsed >= max_wait_seconds:
                raise TimeoutError(f"Timed out acquiring index lock at {lock_path}")

            # 2. Sleep
            time.sleep(sleep_time)

    try:
        yield lock_file
    except Exception:
        # On any exception, remove the lock file and re-raise
        lock_file.close()
        if lock_path.exists():
            lock_path.unlink()
        raise
    else:
        # On successful exit, close the file and atomically rename
        lock_file.close()
        os.replace(lock_path, index_path)


def merge_index(target_path: str, new_hash: str | None, index_path: Path) -> None:
    """Merge a single entry into the index using a streaming zipper pattern.

    :param target_path: The repository-relative path to update in the index.
    :param new_hash: The hash to write for the path, or None to delete the entry.
    :param index_path: Path to the index file.
    """
    with index_lock_file(index_path) as lock_file:
        # Case 1: Index doesn't exist yet. Simply create it with the new entry.
        if not index_path.exists():
            if new_hash is not None:
                lock_file.write(f'{target_path} {new_hash}\n')
            return

        # Case 2: Index exists. Stream and merge.
        inserted = False
        with open(index_path, 'r', encoding='utf-8') as old_index:
            for line in old_index:
                line = line.rstrip('\n\r')
                if not line:
                    continue

                parts = line.rsplit(' ', 1)
                if len(parts) != 2:
                    warnings.warn(f"Skipping malformed index line: {line!r}", RuntimeWarning)
                    continue

                current_path, current_hash = parts

                if current_path < target_path:
                    lock_file.write(f'{current_path} {current_hash}\n')
                elif current_path == target_path:
                    if new_hash is not None:
                        lock_file.write(f'{target_path} {new_hash}\n')
                    inserted = True
                else:
                    if not inserted and new_hash is not None:
                        lock_file.write(f'{target_path} {new_hash}\n')
                        inserted = True
                    lock_file.write(f'{current_path} {current_hash}\n')

        # Case 3: We reached the end of the file and the new entry is last alphabetically
        if not inserted and new_hash is not None:
            lock_file.write(f'{target_path} {new_hash}\n')


def normalize_path(path: str | Path, working_dir: Path) -> str:
    """Resolve, normalize, and validate a path relative to the working directory.

    :param path: The file path to normalize. Can be absolute or relative.
    :param working_dir: The repository working directory.
    :return: A normalized repository-relative path string with forward slashes.
    :raises ValueError: If the path is not within the working directory.
    """
    # Resolve converts relative paths to absolute and cleans up ".." or symlinks
    path_obj = Path(path)
    
    # Ensure working_dir is absolute
    working_dir = Path(os.path.abspath(working_dir))

    # FIX: If path is relative, anchor it to the repo's working directory
    if not path_obj.is_absolute():
        file_path = Path(os.path.abspath(working_dir / path_obj))
    else:
        file_path = Path(os.path.abspath(path_obj))

    # Make path relative to working directory
    try:
        repo_relative_path = file_path.relative_to(working_dir)
    except ValueError:
        msg = f'Path {path} is not within the working directory {working_dir}'
        raise ValueError(msg)

    # Convert to a repository-relative string with forward slashes for cross-platform compatibility
    normalized_path = repo_relative_path.as_posix()

    return normalized_path


def update_index(path: Path | str, index_path: Path, working_dir: Path, repo_dir_name: str, objects_dir: Path | None = None, remove: bool = False) -> None:
    """Update the index with a file path.

    This method generates a blob from the file content, saves it, and updates
    the index with the repository-relative path and the new blob hash.
    If remove is True, the file is removed from the index.

    :param path: The file path to add or update in the index.
    :param index_path: Path to the index file.
    :param working_dir: The repository working directory.
    :param repo_dir_name: The name of the repository directory (e.g. .caf).
    :param objects_dir: The path to the objects directory. Required if remove is False.
    :param remove: If True, remove the file from the index.
    :raises ValueError: If the path is inside the repository directory.
    """
    rel_path = normalize_path(path, working_dir)

    rel_parts = Path(rel_path).parts
    repo_dir_name_cf = repo_dir_name.casefold()
    if any(part.casefold() == repo_dir_name_cf for part in rel_parts):
        msg = f'Cannot index files inside repository directory: {rel_path}'
        raise ValueError(msg)

    if remove:
        merge_index(rel_path, None, index_path=index_path)
    else:
        if objects_dir is None:
            raise ValueError("objects_dir is required when adding to index")
        
        full_path = working_dir / rel_path
        blob = save_file_content(objects_dir, full_path)
        merge_index(rel_path, blob.hash, index_path=index_path)


def read_index(index_path: Path) -> dict[str, str]:
    """Read the index file and return a dictionary of paths to hashes.

    :param index_path: Path to the index file.
    :return: A dictionary mapping file paths (repository-relative) to their
        SHA-1 hashes. Returns an empty dictionary if the index file does not exist.
    """
    index_dict: dict[str, str] = {}

    # If index doesn't exist, return empty dict
    if not index_path.exists():
        return index_dict

    # Stream the index file line-by-line
    with open(index_path, 'r', encoding='utf-8') as index_file:
        for line in index_file:
            # Parse the line: PATH HASH
            line = line.rstrip('\n\r')
            if not line:
                # Skip empty lines
                continue

            # Split on last space to separate path from hash
            parts = line.rsplit(' ', 1)
            if len(parts) != 2:
                # Skip malformed lines
                continue

            path, hash_ = parts
            index_dict[path] = hash_

    return index_dict


def build_tree_from_index(index: dict[str, str], objects_dir: Path) -> str:
    """Build a Tree object from the index and save it to the objects directory.

    :param index: The index dictionary mapping paths to hashes.
    :param objects_dir: The path to the objects directory.
    :return: The hash of the root tree.
    """
    # 1. Build Trie
    # Represents the directory structure as nested dictionaries.
    # Leaves are strings (file hashes), nodes are dictionaries (subdirectories).
    root: dict[str, str | dict] = {}
    
    for path_str, file_hash in index.items():
        parts = Path(path_str).parts
        current = root
        for part in parts[:-1]:
            # Ensure we are navigating into a dictionary.
            if part not in current:
                current[part] = {}
            # If an entry already exists and is a string, it represents a file, but
            # we are now trying to treat it as a directory.
            if isinstance(current[part], str):
                msg = f"Conflict detected: '{part}' is both a file and a directory."
                raise ValueError(msg)
                
            current = current[part]  # type: ignore
        
        current[parts[-1]] = file_hash

    return _build_tree_recursive(root, objects_dir)


def _build_tree_recursive(node: dict[str, str | dict], objects_dir: Path) -> str:
    """Recursively build Tree objects from a Trie node.

    :param node: A dictionary representing a directory node or a file leaf.
    :param objects_dir: Path to objects directory.
    :return: The hash of the saved Tree object.
    """
    tree_records: dict[str, TreeRecord] = {}

    for name in node.keys():
        value = node[name]
        if isinstance(value, dict):
            # Directory: Recursively build its tree first
            subtree_hash = _build_tree_recursive(value, objects_dir)
            tree_records[name] = TreeRecord(TreeRecordType.TREE, subtree_hash, name)
        else:
            # File: Create a BLOB record
            tree_records[name] = TreeRecord(TreeRecordType.BLOB, value, name)

    # Create Tree object
    tree = Tree(tree_records)
    save_tree(objects_dir, tree)
    return hash_object(tree)
