"""Merge functionality for libcaf."""

import mmap
import os
import merge3
from contextlib import ExitStack
from collections.abc import Sequence, Iterator
from pathlib import Path
from typing import overload

from .plumbing import load_commit, load_tree, save_file_content
from .checkout import write_blob
from .ref import HashRef
from . import TreeRecordType, index
from dataclasses import dataclass
import tempfile
import shutil

class FileLineSequence(Sequence[str]):
    """A lazy sequence of lines from a file on disk using mmap."""
    def __init__(self, path: Path):
        self.path = path
        self._offsets: list[int] = [0]
        self._len = 0
        self._file = None
        self._mm = None
        self._scanned_up_to = 0
        self._is_fully_scanned = False
        self._file_size = -1

    def _ensure_open(self):
        """Open file and mmap if not already open."""
        if self._file is None:
            if not self.path.exists():
                self._file_size = 0
                self._is_fully_scanned = True
                return

            self._file_size = self.path.stat().st_size
            if self._file_size == 0:
                self._is_fully_scanned = True
                return

            self._file = self.path.open('rb')
            self._mm = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)

    def _scan_until(self, target_index: int):
        """Scan file until we find the target line index or EOF."""
        self._ensure_open()
        
        if self._is_fully_scanned or not self._mm:
            return

        # Target index 10 means we need 11 offsets (0..10)
        # If target is -1 (infinity), loop until break
        
        while not self._is_fully_scanned:
            if target_index != -1 and len(self._offsets) > target_index + 1:
                return

            pos = self._mm.find(b'\n', self._scanned_up_to)
            if pos == -1:
                # No more newlines
                if self._scanned_up_to < self._file_size:
                    # Last line without newline
                    self._len += 1
                    self._offsets.append(self._file_size)
                self._is_fully_scanned = True
                break
            
            self._len += 1
            self._offsets.append(pos + 1)
            self._scanned_up_to = pos + 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._mm:
            self._mm.close()
        if self._file:
            self._file.close()

    def __len__(self) -> int:
        self._scan_until(-1) # Force full scan
        return self._len

    @overload
    def __getitem__(self, index: int) -> str: ...
    
    @overload
    def __getitem__(self, index: slice) -> list[str]: ...

    def __getitem__(self, index: int | slice) -> str | list[str]:
        if isinstance(index, slice):
             # Optimization for simple slices: [start:stop] or [:stop]
             # Avoid full scan if we only need the beginning.
             if (index.step is None or index.step == 1) and \
                (index.stop is not None and index.stop >= 0) and \
                (index.start is None or index.start >= 0):
                 
                 # Scan only as much as needed
                 self._scan_until(index.stop)
                 
                 start = index.start if index.start is not None else 0
                 stop = index.stop
                 
                 # Clamp stop to what we actually found
                 # current known length is (len(_offsets) - 1)
                 known_len = len(self._offsets) - 1
                 if stop > known_len:
                     stop = known_len
                     
                 return [self[i] for i in range(start, stop)]

             # Fallback for complex slices (negative indices, steps, open-ended stops)
             self._scan_until(-1)
             start, stop, step = index.indices(len(self))
             if step != 1: 
                 raise NotImplementedError("Slicing with step != 1 not supported")
             return [self[i] for i in range(start, stop)]
        
        if index < 0:
            self._scan_until(-1) # Negative index needs full length
            index += len(self)
        
        # Ensure we have scanned up to this index
        self._scan_until(index)
        
        if self._is_fully_scanned and index >= len(self):
             raise IndexError("Index out of range")
        
        # If we just scanned, we should have offsets logic ready
        # BUT if index is out of range, _scan_until might have finished early
        if index >= len(self._offsets) - 1:
             raise IndexError("Index out of range")

        start_offset = self._offsets[index]
        end_offset = self._offsets[index+1]
        
        # Ensure open for read (should be open due to scan, but for safety)
        if self._mm:
            line_bytes = self._mm[start_offset:end_offset]
            return line_bytes.decode('utf-8', errors='replace')
        return ""

def merge_content(base: Path, source: Path, other: Path, labels: tuple[str, str] = ('source', 'other')) -> Iterator[str]:
    """Merge content from three file paths (3-way merge).
    
    :param base: Path to the common ancestor file.
    :param source: Path to the source file (e.g., HEAD).
    :param other: Path to the other file (e.g., merging branch).
    :param labels: Tuple of (source_label, other_label) for conflict markers.
    :return: An iterator yielding the merged content line by line.
    """
    with ExitStack() as stack:
        seq_base = stack.enter_context(FileLineSequence(base))
        seq_source = stack.enter_context(FileLineSequence(source))
        seq_other = stack.enter_context(FileLineSequence(other))

        m = merge3.Merge3(seq_base, seq_source, seq_other)
        yield from m.merge_lines(name_a=labels[0], name_b=labels[1])


def merge_base(repo_objects_dir, commit_hash1: str, commit_hash2: str) -> str | None:
    """Find the common ancestor of two commits using simultaneous traversal.
    
    This implementation restricts traversal to the first parent only and
    traverses both histories simultaneously to improve performance.
    
    :param repo_objects_dir: The path to the objects directory.
    :param commit_hash1: The hash of the first commit.
    :param commit_hash2: The hash of the second commit.
    :return: The hash of the common ancestor or None if no common ancestor is found.
    """
    visited = set()
    
    # Initialize cursors for both commits
    curr1: str | None = commit_hash1
    curr2: str | None = commit_hash2
    
    while curr1 is not None or curr2 is not None:
        # Process commit 1
        if curr1 is not None:
            if curr1 in visited:
                return curr1
            visited.add(curr1)
            
            try:
                commit1 = load_commit(repo_objects_dir, HashRef(curr1))
                curr1 = commit1.parents[0] if commit1.parents else None
            except Exception:
                # If we can't load the commit (e.g. at the beginning of repo or error)
                # just stop this branch
                curr1 = None

        # Process commit 2
        if curr2 is not None:
            if curr2 in visited:
                return curr2
            visited.add(curr2)
            
            try:
                commit2 = load_commit(repo_objects_dir, HashRef(curr2))
                curr2 = commit2.parents[0] if commit2.parents else None
            except Exception:
                curr2 = None
                
    return None

def _get_all_files_from_tree(objects_dir: Path, root_tree_hash: str) -> dict[str, str]:
    """Iteratively collect all files from a directory tree into a dictionary.

    :param objects_dir: Path to objects directory.
    :param root_tree_hash: The hash of the tree to traverse.
    :return: A dictionary mapping relative paths to blob hashes.
    """
    files: dict[str, str] = {}
    if not root_tree_hash:
        return files

    # Stack stores tuples of (tree_hash, path_prefix)
    stack = [(root_tree_hash, "")]

    while stack:
        current_hash, prefix = stack.pop()
        
        # This will raise exceptions if the tree object is missing or corrupt,
        # ensuring we don't silently create an empty directory state.
        tree = load_tree(objects_dir, current_hash)
        
        for name, record in tree.records.items():
            path_str = f"{prefix}/{name}" if prefix else name
            
            if record.type == TreeRecordType.BLOB:
                files[path_str] = record.hash
            elif record.type == TreeRecordType.TREE:
                # Push subdirectory to stack
                stack.append((record.hash, path_str))
                
    return files

def merge_commits(
    objects_dir: Path,
    working_dir: Path,
    index_path: Path,
    head_commit_hash: str,
    other_commit_hash: str,
    base_commit_hash: str | None,
    other_ref_str: str
) -> None:
    """Perform a 3-way merge between HEAD, other, and base.

    :param objects_dir: Path to objects directory.
    :param working_dir: Path to working directory.
    :param index_path: Path to index file.
    :param head_commit_hash: Hash of the HEAD commit.
    :param other_commit_hash: Hash of the other commit.
    :param base_commit_hash: Hash of the base commit (or None).
    :param other_ref_str: Name of the other ref for conflict labels.
    """
    head_commit = load_commit(objects_dir, HashRef(head_commit_hash))
    other_commit = load_commit(objects_dir, HashRef(other_commit_hash))
    base_commit = load_commit(objects_dir, HashRef(base_commit_hash)) if base_commit_hash else None
    
    files_head = _get_all_files_from_tree(objects_dir, head_commit.tree_hash)
    files_other = _get_all_files_from_tree(objects_dir, other_commit.tree_hash)
    files_base = _get_all_files_from_tree(objects_dir, base_commit.tree_hash) if base_commit else {}
    
    all_paths = set(files_head.keys()) | set(files_other.keys()) | set(files_base.keys())
    
    @dataclass
    class MergeAction:
            type: str 
            path: Path
            path_str: str
            blob_hash: str | None = None
            
    actions: list[MergeAction] = []
    
    for path_str in all_paths:
        h_base = files_base.get(path_str)
        h_head = files_head.get(path_str)
        h_other = files_other.get(path_str)
        
        path = working_dir / path_str
        
        if h_head == h_other:
            continue 
        
        if h_head == h_base and h_other != h_base:
            if h_other is None:
                # Deleted in other
                actions.append(MergeAction('DELETE', path, path_str))
            else:
                # Added or Modified in other
                actions.append(MergeAction('UPDATE', path, path_str, h_other))
        
        elif h_other == h_base and h_head != h_base:
            continue
            
        else:
            # Conflict
            actions.append(MergeAction('CONFLICT', path, path_str, h_other))

    index_data = index.read_index(index_path)
    
    for action in actions:
            if action.type == 'DELETE':
                if action.path.exists():
                    if action.path.is_file():
                        os.remove(action.path)
                    elif action.path.is_dir():
                        shutil.rmtree(action.path)
                
                # Update in-memory index
                if action.path_str in index_data:
                    del index_data[action.path_str]
                    
            elif action.type == 'UPDATE':
                if action.path.exists() and action.path.is_dir():
                    shutil.rmtree(action.path)
                write_blob(objects_dir, action.blob_hash, action.path)
                index_data[action.path_str] = action.blob_hash
                
            elif action.type == 'CONFLICT':
                h_base = files_base.get(action.path_str)
                h_head = files_head.get(action.path_str)
                h_other = files_other.get(action.path_str)
                
                with tempfile.TemporaryDirectory() as tmpdirname:
                    tmpdir = Path(tmpdirname)
                    p_base = tmpdir / "base"
                    p_source = tmpdir / "source" 
                    p_other = tmpdir / "other"
                    
                    if h_base: write_blob(objects_dir, h_base, p_base)
                    else: p_base.touch()
                        
                    if h_head: write_blob(objects_dir, h_head, p_source)
                    elif action.path.is_file(): 
                        shutil.copy2(action.path, p_source)
                    else: p_source.write_text("")

                    if h_other: write_blob(objects_dir, h_other, p_other)
                    else: p_other.write_text("")
                        
                    merged_lines = merge_content(p_base, p_source, p_other, labels=("HEAD", other_ref_str))
                    
                    action.path.parent.mkdir(parents=True, exist_ok=True)
                    if action.path.exists() and action.path.is_dir():
                        shutil.rmtree(action.path)
                        
                    action.path.write_text("".join(merged_lines))
                    
                    blob = save_file_content(objects_dir, action.path)
                    index_data[action.path_str] = blob.hash

    index.write_index(index_path, index_data)
