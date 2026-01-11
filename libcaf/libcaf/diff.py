from collections import deque
from collections.abc import Sequence, Callable
from dataclasses import dataclass
from pathlib import Path

from . import Tree, TreeRecord, TreeRecordType
from .plumbing import hash_file, hash_object, load_tree


class DiffError(Exception):
    """Exception raised for diff-related errors."""


@dataclass
class Diff:
    """A class representing a difference between two tree records."""

    record: TreeRecord
    parent: "Diff | None"
    children: list["Diff"]


@dataclass
class AddedDiff(Diff):
    """An added tree record diff as part of a commit."""


@dataclass
class RemovedDiff(Diff):
    """A removed tree record diff as part of a commit."""


@dataclass
class ModifiedDiff(Diff):
    """A modified tree record diff as part of a commit."""
    new_record: TreeRecord | None = None


@dataclass
class MovedToDiff(Diff):
    """A tree record diff that has been moved elsewhere as part of a commit."""

    moved_to: "MovedFromDiff | None"


@dataclass
class MovedFromDiff(Diff):
    """A tree record diff that has been moved from elsewhere as part of a commit."""

    moved_from: MovedToDiff | None


def build_tree_from_fs(path: Path, *, repo_dir_name: str) -> tuple[Tree, str, dict[str, Tree]]:
    """Build an in-memory Tree for the given filesystem directory.

    :param path: The directory path to build the tree from.
    :param repo_dir_name: The repository directory name to ignore (e.g. '.caf').
    :return: A tuple of (root_tree, root_hash, tree_lookup), where tree_lookup maps tree hashes
        to Tree objects for subtrees built from the filesystem.
    :raises NotADirectoryError: If the given path does not exist or is not a directory.
    """
    if not path or not path.is_dir():
        msg = f"{path} is not a directory"
        raise NotADirectoryError(msg)

    dir_hashes: dict[Path, str] = {}
    tree_lookup: dict[str, Tree] = {}
    trees_by_path: dict[Path, Tree] = {}

    stack = deque([path])

    while stack:
        current_path = stack.pop()
        tree_records: dict[str, TreeRecord] = {}

        for item in current_path.iterdir():
            if item.name == repo_dir_name:
                continue

            if item.is_file():
                blob_hash = hash_file(item)
                tree_records[item.name] = TreeRecord(TreeRecordType.BLOB, blob_hash, item.name)

            elif item.is_dir():
                if item in dir_hashes:
                    subtree_hash = dir_hashes[item]
                    tree_records[item.name] = TreeRecord(TreeRecordType.TREE, subtree_hash, item.name)
                else:
                    stack.append(current_path)
                    stack.append(item)
                    break
        else:
            tree = Tree(tree_records)
            tree_hash = hash_object(tree)

            trees_by_path[current_path] = tree
            dir_hashes[current_path] = tree_hash
            tree_lookup[tree_hash] = tree

    root_hash = dir_hashes[path]
    root_tree = trees_by_path[path]
    return root_tree, root_hash, tree_lookup


def diff_trees(tree1: Tree | None, tree2: Tree | None, *, load_tree1: Callable[[str], Tree],
               load_tree2: Callable[[str], Tree]) -> Sequence[Diff]:
    """Generate a diff between two Tree objects.

    :param tree1: The first tree (old side). May be None.
    :param tree2: The second tree (new side). May be None.
    :param load_tree1: Function used to load subtrees for tree1 by hash.
    :param load_tree2: Function used to load subtrees for tree2 by hash.
    :return: A sequence of Diff objects representing the changes.
    :raises DiffError: If a required subtree cannot be loaded.
    """
    top_level_diff = Diff(TreeRecord(TreeRecordType.TREE, "", ""), None, [])
    stack: list[tuple[Tree | None, Tree | None, Diff]] = [(tree1, tree2, top_level_diff)]

    potentially_added: dict[str, AddedDiff] = {}
    potentially_removed: dict[str, RemovedDiff] = {}

    def _expand_diff(diff: AddedDiff | RemovedDiff, tree: Tree) -> None:
        """Recursively expand an added or removed tree diff."""
        for record in tree.records.values():
            if isinstance(diff, AddedDiff):
                child_diff = AddedDiff(record, diff, [])
                potentially_added[record.hash] = child_diff
                diff.children.append(child_diff)
            else:
                child_diff = RemovedDiff(record, diff, [])
                potentially_removed[record.hash] = child_diff
                diff.children.append(child_diff)
            
            if record.type == TreeRecordType.TREE:
                try:
                    # We need to load the subtree to continue expansion
                    # For AddedDiff, we use load_tree2 (new tree)
                    # For RemovedDiff, we use load_tree1 (old tree)
                    loader = load_tree2 if isinstance(diff, AddedDiff) else load_tree1
                    subtree = loader(record.hash)
                    _expand_diff(child_diff, subtree)
                except Exception:
                    # If we can't load the tree, we just stop implementation for this branch
                    # This might happen if the tree object is missing
                    pass

    def _promote_parents_to_modified(diff: Diff) -> None:
        """Promote parent Added/Removed diffs to Modified diffs recursively."""
        curr = diff.parent
        while curr and curr.parent: # Stop before top_level_diff
            if isinstance(curr, (AddedDiff, RemovedDiff)):
                # Convert to ModifiedDiff
                new_diff = ModifiedDiff(curr.record, curr.parent, curr.children, new_record=None)
                
                # We need to update the parent's children list to point to the new diff
                # and update all children to point to the new parent
                new_children_list = []
                for child in curr.parent.children:
                    if child is curr:
                        new_children_list.append(new_diff)
                    else:
                        new_children_list.append(child)
                curr.parent.children = new_children_list
                
                for child in curr.children:
                    child.parent = new_diff
                
                curr = new_diff
            curr = curr.parent

    while stack:
        current_tree1, current_tree2, parent_diff = stack.pop()
        records1 = current_tree1.records if current_tree1 else {}
        records2 = current_tree2.records if current_tree2 else {}

        for name, record1 in records1.items():
            if name not in records2:
                if record1.hash in potentially_added:
                    added_diff = potentially_added[record1.hash]
                    del potentially_added[record1.hash]

                    # Found a move!
                    local_diff = MovedToDiff(record1, parent_diff, [], None)
                    moved_from_diff = MovedFromDiff(added_diff.record, added_diff.parent, [], local_diff)
                    local_diff.moved_to = moved_from_diff

                    # Fix up the added_diff side
                    # 1. Update the child reference in the parent's children list
                    added_parent = added_diff.parent
                    new_children = []
                    for child in added_parent.children:
                        if child is added_diff:
                            new_children.append(moved_from_diff)
                        else:
                            new_children.append(child)
                    added_parent.children = new_children

                    # 2. Promote parents if necessary (e.g. if we moved out of a Removed directory into an Added one)
                    _promote_parents_to_modified(moved_from_diff)

                    # 3. If the added diff had children (it was a tree), we need to move them 
                    # FROM the added_diff TO the moved_from_diff
                    moved_from_diff.children = added_diff.children
                    for child in moved_from_diff.children:
                        child.parent = moved_from_diff

                else:
                    local_diff = RemovedDiff(record1, parent_diff, [])
                    potentially_removed[record1.hash] = local_diff
                    
                    # Expand if it is a tree
                    if record1.type == TreeRecordType.TREE:
                         try:
                            subtree = load_tree1(record1.hash)
                            _expand_diff(local_diff, subtree)
                         except Exception:
                            pass

                parent_diff.children.append(local_diff)
            else:
                record2 = records2[name]

                if record1.hash == record2.hash:
                    continue

                if record1.type == TreeRecordType.TREE and record2.type == TreeRecordType.TREE:
                    subtree_diff = ModifiedDiff(record1, parent_diff, [], new_record=record2)

                    try:
                        sub1 = load_tree1(record1.hash)
                        sub2 = load_tree2(record2.hash)
                    except Exception as e:
                        msg = "Error loading subtree for diff"
                        raise DiffError(msg) from e

                    stack.append((sub1, sub2, subtree_diff))
                    parent_diff.children.append(subtree_diff)
                else:
                    parent_diff.children.append(ModifiedDiff(record1, parent_diff, [], new_record=record2))

        for name, record2 in records2.items():
            if name not in records1:
                if record2.hash in potentially_removed:
                    removed_diff = potentially_removed[record2.hash]
                    del potentially_removed[record2.hash]

                    # Found a move!
                    local_diff = MovedFromDiff(record2, parent_diff, [], None)
                    moved_to_diff = MovedToDiff(removed_diff.record, removed_diff.parent, [], local_diff)
                    local_diff.moved_from = moved_to_diff

                    # Fix up the removed_diff side
                    removed_parent = removed_diff.parent
                    new_children = []
                    for child in removed_parent.children:
                        if child is removed_diff:
                            new_children.append(moved_to_diff)
                        else:
                            new_children.append(child)
                    removed_parent.children = new_children

                    _promote_parents_to_modified(moved_to_diff)

                    moved_to_diff.children = removed_diff.children
                    for child in moved_to_diff.children:
                        child.parent = moved_to_diff

                else:
                    local_diff = AddedDiff(record2, parent_diff, [])
                    potentially_added[record2.hash] = local_diff

                    # Expand if it is a tree
                    if record2.type == TreeRecordType.TREE:
                         try:
                            subtree = load_tree2(record2.hash)
                            _expand_diff(local_diff, subtree)
                         except Exception:
                            pass

                parent_diff.children.append(local_diff)

    return top_level_diff.children