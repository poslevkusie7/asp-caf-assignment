from libcaf.constants import DEFAULT_REPO_DIR, HEAD_FILE

from caf import cli_commands


def test_log_command(temp_repo, parse_commit_hash, capsys):
    temp_file = temp_repo / 'log_test.txt'
    temp_file.write_text('First commit content')

    assert cli_commands.commit(working_dir_path=temp_repo,
                               author='Log Tester', message='First commit') == 0
    commit_hash1 = parse_commit_hash()

    temp_file.write_text('Second commit content')
    assert cli_commands.commit(working_dir_path=temp_repo,
                               author='Log Tester', message='Second commit') == 0
    commit_hash2 = parse_commit_hash()

    assert cli_commands.log(working_dir_path=temp_repo) == 0

    output = capsys.readouterr().out
    assert commit_hash1 in output
    assert commit_hash2 in output
    assert 'Log Tester' in output
    assert 'First commit' in output
    assert 'Second commit' in output


def test_log_no_repo(temp_repo_dir, capsys):
    assert cli_commands.log(working_dir_path=temp_repo_dir) == -1
    assert 'No repository found' in capsys.readouterr().err


def test_log_repo_error(temp_repo, capsys):
    (temp_repo / DEFAULT_REPO_DIR / HEAD_FILE).unlink()
    assert cli_commands.log(working_dir_path=temp_repo) == -1

    assert 'Repository error' in capsys.readouterr().err


def test_log_no_commits(temp_repo, capsys):
    assert cli_commands.log(working_dir_path=temp_repo) == 0
    assert 'No commits in the repository' in capsys.readouterr().out
