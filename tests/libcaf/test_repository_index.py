import json
from pathlib import Path
from libcaf.repository import Repository, RepositoryError
from pytest import raises

def test_index_path(temp_repo: Repository) -> None:
    """Test that index_path returns the correct path."""
    expected_path = temp_repo.repo_path() / 'index'
    assert temp_repo.index_path() == expected_path

def test_read_index_empty_when_missing(temp_repo: Repository) -> None:
    """Test that read_index returns an empty dictionary if the index file does not exist."""
    # Ensure index file is not present
    index_path = temp_repo.index_path()
    if index_path.exists():
        index_path.unlink()
    
    assert temp_repo.read_index() == {}

def test_write_read_roundtrip(temp_repo: Repository) -> None:
    """Test writing data to the index and reading it back."""
    data = {
        'file1.txt': {'hash': 'abc1234'},
        'dir/file2.txt': {'hash': 'def5678'}
    }
    
    temp_repo.write_index(data)
    
    # Read back and verify
    loaded_data = temp_repo.read_index()
    assert loaded_data == data

    # Verify formatting (optional but good for debugging)
    index_path = temp_repo.index_path()
    with index_path.open('r') as f:
        content = json.load(f)
    assert content == data

def test_read_invalid_json_raises_error(temp_repo: Repository) -> None:
    """Test that reading a corrupted index file raises RepositoryError."""
    index_path = temp_repo.index_path()
    
    # Write invalid JSON
    with index_path.open('w') as f:
        f.write('{ invalid json')
        
    with raises(RepositoryError, match='Invalid index file'):
        temp_repo.read_index()

def test_update_index_file(temp_repo: Repository) -> None:
    """Test adding a single file to the index."""
    foo = temp_repo.working_dir / 'foo.txt'
    foo.write_text('content')
    
    temp_repo.update_index(foo)
    
    index = temp_repo.read_index()
    assert 'foo.txt' in index
    assert 'hash' in index['foo.txt']

def test_update_index_directory(temp_repo: Repository) -> None:
    """Test adding a directory recursively."""
    subdir = temp_repo.working_dir / 'subdir'
    subdir.mkdir()
    (subdir / 'bar.txt').write_text('bar')
    (subdir / 'baz.txt').write_text('baz')
    
    temp_repo.update_index(subdir)
    
    index = temp_repo.read_index()
    assert 'subdir/bar.txt' in index
    assert 'subdir/baz.txt' in index

def test_update_index_modifies_hash(temp_repo: Repository) -> None:
    """Test that updating an existing file updates its hash."""
    foo = temp_repo.working_dir / 'foo.txt'
    foo.write_text('version1')
    temp_repo.update_index(foo)
    hash1 = temp_repo.read_index()['foo.txt']['hash']
    
    foo.write_text('version2')
    temp_repo.update_index(foo)
    hash2 = temp_repo.read_index()['foo.txt']['hash']
    
    assert hash1 != hash2

def test_update_index_outside_repo_raises_error(temp_repo: Repository, tmp_path: Path) -> None:
    """Test that adding a file outside the repo raises ValueError."""
    outside_file = tmp_path / 'outside.txt'
    outside_file.write_text('outside')
    
    with raises(ValueError, match='outside the repository'):
        temp_repo.update_index(outside_file)

def test_update_index_nonexistent_raises_error(temp_repo: Repository) -> None:
    """Test that adding a non-existent path raises ValueError."""
    non_existent = temp_repo.working_dir / 'does_not_exist'
    
    with raises(ValueError, match='does not exist'):
        temp_repo.update_index(non_existent)
