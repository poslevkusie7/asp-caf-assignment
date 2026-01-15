"""Merge functionality for libcaf."""

from .plumbing import load_commit
from .ref import HashRef
from .constants import OBJECTS_SUBDIR

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
