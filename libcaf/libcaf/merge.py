"""Merge functionality for libcaf."""

import mmap
import os
import merge3
from contextlib import ExitStack
from collections.abc import Sequence, Iterator
from pathlib import Path
from typing import overload

from .plumbing import load_commit
from .ref import HashRef

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
