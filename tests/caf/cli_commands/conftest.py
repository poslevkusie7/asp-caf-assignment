from pytest import fixture

from caf import cli_commands


@fixture
def temp_repo(temp_repo_dir):
    assert cli_commands.init(working_dir_path=temp_repo_dir) == 0
    return temp_repo_dir


@fixture
def parse_commit_hash(capsys):
    def _parse():
        out = capsys.readouterr().out

        hash = None
        for line in out.splitlines():
            if line.startswith('Hash:'):
                hash = line.split(':', 1)[1].strip()

        return hash

    return _parse
