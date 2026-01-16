"""Merge functionality for libcaf."""

import difflib
from dataclasses import dataclass

from .plumbing import load_commit
from .ref import HashRef
from .constants import OBJECTS_SUBDIR

@dataclass
class _Change:
    start: int
    end: int
    lines: list[str]
    origin: str

def _get_changes(base_lines: list[str], text_lines: list[str], origin: str) -> list[_Change]:
    matcher = difflib.SequenceMatcher(None, base_lines, text_lines)
    changes = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != 'equal':
            changes.append(_Change(i1, i2, text_lines[j1:j2], origin))
    return changes

def _apply_changes_to_base_substring(base_lines: list[str], start: int, end: int, changes_subset: list[_Change]) -> list[str]:
    res = []
    curr = start
    for c in changes_subset:
        if c.start > curr:
            res.extend(base_lines[curr:c.start])
        res.extend(c.lines)
        curr = c.end
    if curr < end:
        res.extend(base_lines[curr:end])
    return res

def merge_content(base: str, source: str, other: str) -> str:
    """Merge content from three sources (3-way merge).
    
    :param base: The common ancestor content.
    :param source: The source content (e.g., HEAD).
    :param other: The other content (e.g., merging branch).
    :return: The merged content with conflict markers.
    """
    base_lines = base.splitlines(keepends=True)
    source_lines = source.splitlines(keepends=True)
    other_lines = other.splitlines(keepends=True)

    changes_source = _get_changes(base_lines, source_lines, 'source')
    changes_other = _get_changes(base_lines, other_lines, 'other')
    
    all_changes = sorted(changes_source + changes_other, key=lambda c: c.start)
    
    output = []
    base_idx = 0
    change_idx = 0
    
    while change_idx < len(all_changes):
        change = all_changes[change_idx]
        
        if change.start > base_idx:
            output.extend(base_lines[base_idx:change.start])
            base_idx = change.start
        
        cluster = [change]
        change_idx += 1
        
        cluster_start = change.start
        cluster_end = change.end
        
        while change_idx < len(all_changes):
            next_change = all_changes[change_idx]
            
            is_overlap = False
            if next_change.start < cluster_end:
                is_overlap = True
            elif next_change.start == cluster_end:
                if next_change.end == next_change.start:
                     is_overlap = True
                else: 
                     is_overlap = False
            
            if is_overlap:
                cluster.append(next_change)
                cluster_end = max(cluster_end, next_change.end)
                change_idx += 1
            else:
                break

        cluster_source = [c for c in cluster if c.origin == 'source']
        cluster_other = [c for c in cluster if c.origin == 'other']
        
        res_source = _apply_changes_to_base_substring(base_lines, cluster_start, cluster_end, cluster_source)
        res_other = _apply_changes_to_base_substring(base_lines, cluster_start, cluster_end, cluster_other)
        
        if not cluster_source:
             output.extend(res_other)
        elif not cluster_other:
             output.extend(res_source)
        else:
             if res_source == res_other:
                 output.extend(res_source)
             else:
                 output.append("<<<<<<< source\n")
                 output.extend(res_source)
                 output.append("=======\n")
                 output.extend(res_other)
                 output.append(">>>>>>> other\n")
            
        base_idx = cluster_end

    if base_idx < len(base_lines):
        output.extend(base_lines[base_idx:])
        
    return "".join(output)

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
