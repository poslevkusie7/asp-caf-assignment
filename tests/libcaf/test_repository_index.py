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
