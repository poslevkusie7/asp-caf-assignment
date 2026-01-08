from libcaf.repository import Repository
from caf import cli_commands

def test_add_single_file(temp_repo: Repository, capsys):
    f = temp_repo.working_dir / 'file.txt'
    f.write_text("content")
    
    ret = cli_commands.add(working_dir_path=str(temp_repo.working_dir), files=[str(f)])
    
    assert ret == 0
    out, err = capsys.readouterr()
    assert "Added file.txt" in out
    
    index = temp_repo.read_index()
    assert 'file.txt' in index

def test_add_multiple_files(temp_repo: Repository, capsys):
    f1 = temp_repo.working_dir / 'f1.txt'
    f1.write_text("c1")
    f2 = temp_repo.working_dir / 'f2.txt'
    f2.write_text("c2")
    
    ret = cli_commands.add(working_dir_path=str(temp_repo.working_dir), files=[str(f1), str(f2)])
    
    assert ret == 0
    out, err = capsys.readouterr()
    assert "Added f1.txt" in out
    assert "Added f2.txt" in out
    
    index = temp_repo.read_index()
    assert 'f1.txt' in index
    assert 'f2.txt' in index

def test_add_missing_file(temp_repo: Repository, capsys):
    ret = cli_commands.add(working_dir_path=str(temp_repo.working_dir), files=["ghost.txt"])
    
    assert ret == -1
    out, err = capsys.readouterr()
    assert "File ghost.txt does not exist" in err
    
    assert temp_repo.read_index() == {}

def test_add_file_inside_repo_dir(temp_repo: Repository, capsys):
    f = temp_repo.repo_path() / 'config'
    f.write_text("secret")
    
    ret = cli_commands.add(working_dir_path=str(temp_repo.working_dir), files=[str(f)])
    
    assert ret == -1
    out, err = capsys.readouterr()
    assert "Error: Cannot index files inside repository directory" in err

def test_add_no_repo(tmp_path, capsys):
    f = tmp_path / 'orphan.txt'
    f.touch()
    
    ret = cli_commands.add(working_dir_path=str(tmp_path), files=[str(f)])
    
    assert ret == -1
    out, err = capsys.readouterr()
    assert "No repository found" in err

def test_add_directory(temp_repo: Repository, capsys):
    subdir = temp_repo.working_dir / 'subdir'
    subdir.mkdir()
    f1 = subdir / 'f1.txt'
    f1.write_text("c1")
    f2 = subdir / 'f2.txt'
    f2.write_text("c2")
    
    # Attempt to add the directory
    ret = cli_commands.add(working_dir_path=str(temp_repo.working_dir), files=[str(subdir)])
    
    assert ret == 0
    out, err = capsys.readouterr()
    
    index = temp_repo.read_index()
    assert 'subdir/f1.txt' in index
    assert 'subdir/f2.txt' in index

def test_add_nested_file_explicitly(temp_repo: Repository, capsys):
    subdir = temp_repo.working_dir / 'src'
    subdir.mkdir()
    f = subdir / 'main.py'
    f.write_text("print('hello')")
    
    ret = cli_commands.add(working_dir_path=str(temp_repo.working_dir), files=[str(f)])
    
    assert ret == 0
    out, err = capsys.readouterr()
    # Check normalized path in output
    assert "Added src/main.py" in out
    
    index = temp_repo.read_index()
    # Verify exact key in index (normalized, forward slashes)
    assert 'src/main.py' in index
