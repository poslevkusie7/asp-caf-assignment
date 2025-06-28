from caf import cli_commands


def test_delete_repo_command(temp_repo, capsys):
    assert (temp_repo / '.caf').exists()
    assert cli_commands.delete_repo(working_dir_path=temp_repo) == 0
    assert 'Deleted repository' in capsys.readouterr().out

    assert not (temp_repo / '.caf').exists()
    assert cli_commands.delete_repo(working_dir_path=temp_repo) == -1
    assert 'No repository found' in capsys.readouterr().err


def test_delete_repo_no_repo(temp_repo_dir, capsys):
    assert not (temp_repo_dir / '.caf').exists()
    assert cli_commands.delete_repo(working_dir_path=temp_repo_dir) == -1
    assert 'No repository found' in capsys.readouterr().err
