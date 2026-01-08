import pytest
from libcaf.index import build_tree_from_index
from libcaf.plumbing import hash_object
from libcaf import Tree, TreeRecord, TreeRecordType

def test_build_tree_empty(temp_repo):
    objects_dir = temp_repo.objects_dir()
    index = {}
    
    tree_hash = build_tree_from_index(index, objects_dir)
    
    # Empty tree hash
    empty_tree = Tree({})
    assert tree_hash == hash_object(empty_tree)

def test_build_tree_flat(tmp_path):
    objects_dir = tmp_path / "objects"
    objects_dir.mkdir()
    h1 = "a" * 40
    h2 = "b" * 40
    index = {
        "file1.txt": h1,
        "file2.txt": h2
    }
    
    tree_hash = build_tree_from_index(index, objects_dir)
    
    records = {
        "file1.txt": TreeRecord(TreeRecordType.BLOB, h1, "file1.txt"),
        "file2.txt": TreeRecord(TreeRecordType.BLOB, h2, "file2.txt")
    }
    expected_tree = Tree(records)
    assert tree_hash == hash_object(expected_tree)

def test_build_tree_nested(tmp_path):
    objects_dir = tmp_path / "objects"
    objects_dir.mkdir()
    h1 = "a" * 40
    h2 = "b" * 40
    index = {
        "root.txt": h1,
        "subdir/deep.txt": h2
    }
    
    tree_hash = build_tree_from_index(index, objects_dir)
    
    subdir_records = {
        "deep.txt": TreeRecord(TreeRecordType.BLOB, h2, "deep.txt")
    }
    subdir_tree = Tree(subdir_records)
    subdir_hash = hash_object(subdir_tree)
    
    root_records = {
        "root.txt": TreeRecord(TreeRecordType.BLOB, h1, "root.txt"),
        "subdir": TreeRecord(TreeRecordType.TREE, subdir_hash, "subdir")
    }
    root_tree = Tree(root_records)
    
    assert tree_hash == hash_object(root_tree)

def test_build_tree_file_dir_conflict(tmp_path):
    objects_dir = tmp_path / "objects"
    objects_dir.mkdir()
    h1 = "a" * 40
    h2 = "b" * 40
    
    index = {
        "data": h1,
        "data/config.txt": h2
    }
    with pytest.raises(ValueError, match="Conflict"):
        build_tree_from_index(index, objects_dir)

def test_build_tree_deterministic_sorting(tmp_path):
    objects_dir = tmp_path / "objects"
    objects_dir.mkdir()
    h1 = "1" * 40
    h2 = "2" * 40
    h3 = "3" * 40
    
    # Create two indexes with same content but different insertion order
    index1 = {
        "a.txt": h1,
        "b.txt": h2,
        "c/d.txt": h3
    }
    
    index2 = {
        "c/d.txt": h3,
        "b.txt": h2,
        "a.txt": h1
    }
    
    hash1 = build_tree_from_index(index1, objects_dir)
    hash2 = build_tree_from_index(index2, objects_dir)
    
    # Hash MUST be identical
    assert hash1 == hash2
