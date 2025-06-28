from caf import cli_commands


def test_branch_exists_command(temp_repo, capsys):
    assert cli_commands.add_branch(working_dir_path=temp_repo, branch_name='feature') == 0
    assert cli_commands.branch_exists(working_dir_path=temp_repo, branch_name='feature') == 0

    assert 'exists' in capsys.readouterr().out


def test_branch_exists_no_repo(temp_repo_dir, capsys):
    assert cli_commands.branch_exists(working_dir_path=temp_repo_dir, branch_name='feature') == -1

    assert 'No repository found' in capsys.readouterr().err


def test_branch_exists_empty(temp_repo, capsys):
    assert cli_commands.branch_exists(working_dir_path=temp_repo, branch_name='') == -1
    assert 'Branch name is required' in capsys.readouterr().err


def test_branch_exists_does_not_exist(temp_repo, capsys):
    assert cli_commands.branch_exists(working_dir_path=temp_repo, branch_name='branch') == -1
    assert 'Branch "branch" does not exist' in capsys.readouterr().err
