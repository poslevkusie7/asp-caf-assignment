from pytest import raises
from libcaf.repository import Repository

def _get_hash(repo: Repository, path: str) -> str:
    """Helper to get expected hash for a file in the working dir."""
    # We resolve path relative to working dir manually here for test setup
    return repo.save_file_content(repo.working_dir / path).hash

def test_index_initially_empty(temp_repo: Repository) -> None:
    """Test that a fresh repository has an empty index."""
    assert temp_repo.read_index() == {}

def test_index_persistence(temp_repo: Repository) -> None:
    """Test that added entries persist."""
    # Setup
    f = temp_repo.working_dir / 'file.txt'
    f.touch()
    expected_hash = _get_hash(temp_repo, 'file.txt')
    
    # Action
    temp_repo.update_index('file.txt')
    
    # Verification
    index = temp_repo.read_index()
    assert index['file.txt'] == expected_hash
    assert len(index) == 1

def test_index_updates(temp_repo: Repository) -> None:
    """Test that updating an existing entry changes the hash."""
    f = temp_repo.working_dir / 'file.txt'
    f.write_text("v1")
    hash_v1 = _get_hash(temp_repo, 'file.txt')
    
    temp_repo.update_index('file.txt')
    assert temp_repo.read_index()['file.txt'] == hash_v1

    f.write_text("v2")
    hash_v2 = _get_hash(temp_repo, 'file.txt')
    temp_repo.update_index('file.txt')

    assert temp_repo.read_index()['file.txt'] == hash_v2

def test_index_removals(temp_repo: Repository) -> None:
    """Test removing entries from the index."""
    (temp_repo.working_dir / 'file.txt').touch()
    temp_repo.update_index('file.txt')
    
    # Action
    temp_repo.remove_from_index('file.txt')
    
    # Verification
    assert temp_repo.read_index() == {}

def test_index_robustness_scenario(temp_repo: Repository) -> None:
    """Test a complex sequence of adds, updates, and removals."""
    # Create necessary files with distinct content
    (temp_repo.working_dir / 'a.txt').write_text("aaa")
    (temp_repo.working_dir / 'b.txt').write_text("bbb")
    (temp_repo.working_dir / 'c.txt').write_text("ccc")
    
    h_a = _get_hash(temp_repo, 'a.txt')
    h_b = _get_hash(temp_repo, 'b.txt')
    h_c = _get_hash(temp_repo, 'c.txt')
    
    # 1. Add unordered
    temp_repo.update_index('b.txt')
    temp_repo.update_index('a.txt')
    temp_repo.update_index('c.txt')
    
    # Verify intermediate state (sorted by key in dict)
    state1 = temp_repo.read_index()
    assert state1 == {
        'a.txt': h_a,
        'b.txt': h_b,
        'c.txt': h_c
    }
    
    # 2. Update one
    (temp_repo.working_dir / 'b.txt').write_text("bbb2")
    h_b2 = _get_hash(temp_repo, 'b.txt')
    temp_repo.update_index('b.txt')
    
    # 3. Remove one
    temp_repo.remove_from_index('a.txt')
    
    # 4. Verify final state
    final_state = temp_repo.read_index()
    assert final_state == {
        'b.txt': h_b2,
        'c.txt': h_c
    }

def test_update_index_security_validation(temp_repo: Repository) -> None:
    """Test that invalid paths are rejected by the public API."""
    outside_file = temp_repo.working_dir.parent / 'outside.txt'
    caf_file = temp_repo.repo_path() / 'config'
    
    with raises(ValueError, match='within the working directory'):
        temp_repo.update_index(outside_file)
        
    with raises(ValueError, match='inside repository directory'):
        temp_repo.update_index(caf_file)

def test_remove_non_existent_is_safe(temp_repo: Repository) -> None:
    """Test that removing a non-indexed file does not crash."""
    (temp_repo.working_dir / 'ghost.txt').touch()
    
    # Action - should complete without error
    temp_repo.remove_from_index('ghost.txt') 
    
    assert temp_repo.read_index() == {}

def test_nested_directory_paths(temp_repo: Repository) -> None:
    """Test that files in subdirectories are correctly normalized and stored in the index."""
    subdir = temp_repo.working_dir / 'subdir'
    subdir.mkdir()
    nested_file = subdir / 'nested.txt'
    nested_file.write_text("nested")
    
    # Create a deep nested path
    deep_subdir = subdir / 'deep'
    deep_subdir.mkdir()
    deep_file = deep_subdir / 'deep_file.txt'
    deep_file.write_text("deep")

    temp_repo.update_index(nested_file)
    temp_repo.update_index(deep_file)

    index = temp_repo.read_index()
    
    # Get expected hashes manually
    h_nested = temp_repo.save_file_content(nested_file).hash
    h_deep = temp_repo.save_file_content(deep_file).hash

    assert index['subdir/nested.txt'] == h_nested
    assert index['subdir/deep/deep_file.txt'] == h_deep
    assert len(index) == 2

def test_update_index_paths_with_spaces_and_special_chars(temp_repo: Repository) -> None:
    """Test update_index with paths containing spaces and special characters."""
    # Create file with spaces
    file_with_spaces = temp_repo.working_dir / 'my file.txt'
    file_with_spaces.touch()
    
    # Create file with special characters (common ones like @, -, _)
    file_with_specials = temp_repo.working_dir / 'file@v1-final_real.txt'
    file_with_specials.touch()

    # Create directory with spaces
    dir_with_spaces = temp_repo.working_dir / 'my folder'
    dir_with_spaces.mkdir()
    file_in_dir_with_spaces = dir_with_spaces / 'inner file.txt'
    file_in_dir_with_spaces.touch()

    # Update index
    temp_repo.update_index('my file.txt')
    temp_repo.update_index('file@v1-final_real.txt')
    temp_repo.update_index('my folder/inner file.txt')

    # Verify
    index = temp_repo.read_index()
    # Empty files
    h_empty = temp_repo.save_file_content(file_with_spaces).hash
    
    assert index['my file.txt'] == h_empty
    assert index['file@v1-final_real.txt'] == h_empty
    assert index['my folder/inner file.txt'] == h_empty


def test_index_update_idempotency_with_multiple_files(temp_repo: Repository) -> None:
    """Test idempotency when multiple files are in the index."""
    # Setup
    f1 = temp_repo.working_dir / 'file1.txt'
    f1.write_text("content1")
    f2 = temp_repo.working_dir / 'file2.txt'
    f2.write_text("content2")
    
    h1 = _get_hash(temp_repo, 'file1.txt')
    h2 = _get_hash(temp_repo, 'file2.txt')

    # 1. Add both files
    temp_repo.update_index('file1.txt')
    temp_repo.update_index('file2.txt')
    
    # 2. Add file1 again
    temp_repo.update_index('file1.txt')
    
    # Verification
    index = temp_repo.read_index()
    assert len(index) == 2
    assert index['file1.txt'] == h1
    assert index['file2.txt'] == h2
    
    # Verify order (read_index returns dict, but Python 3.7+ dicts preserve insertion order, 
    # and read_index logic parses line by line from a sorted file)
    keys = list(index.keys())
    assert keys == ['file1.txt', 'file2.txt']
