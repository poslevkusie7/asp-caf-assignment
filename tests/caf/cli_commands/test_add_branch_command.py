from libcaf.constants import DEFAULT_BRANCH, DEFAULT_REPO_DIR, HEADS_DIR, HEAD_FILE, REFS_DIR

from caf import cli_commands


def test_add_branch_command(temp_repo):
    assert cli_commands.add_branch(working_dir_path=temp_repo, branch_name='feature') == 0

    branch_path = temp_repo / DEFAULT_REPO_DIR / REFS_DIR / HEADS_DIR / 'feature'
    assert branch_path.exists()


def test_add_branch_missing_name(temp_repo, capsys):
    assert cli_commands.add_branch(working_dir_path=temp_repo) == -1
    assert 'Branch name is required' in capsys.readouterr().err


def test_add_branch_twice(temp_repo, capsys):
    assert cli_commands.add_branch(working_dir_path=temp_repo, branch_name='feature') == 0
    assert cli_commands.add_branch(working_dir_path=temp_repo, branch_name='feature') == -1

    assert 'Branch "feature" already exists' in capsys.readouterr().err


def test_add_branch_no_repo(temp_repo_dir, capsys):
    assert cli_commands.add_branch(working_dir_path=temp_repo_dir, branch_name='feature') == -1
    assert 'No repository found at' in capsys.readouterr().err