import tempfile
from pathlib import Path

from libcaf.constants import HASH_LENGTH
from libcaf.ref import HashRef, SymRef, read_ref, write_ref
from pytest import raises


def test_branch_name_with_slash():
    symref = SymRef("refs/heads/main")
    assert symref.branch_name() == "main"


def test_branch_name_without_slash():
    symref = SymRef("main")
    assert symref.branch_name() == "main"


def test_branch_name_multiple_slashes():
    symref = SymRef("refs/remotes/origin/feature-branch")
    assert symref.branch_name() == "feature-branch"


def test_read_symbolic_ref():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("ref: refs/heads/main")
        f.flush()

        result = read_ref(Path(f.name))
        assert isinstance(result, SymRef)
        assert result == "refs/heads/main"


def test_read_empty_ref():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("")
        f.flush()

        result = read_ref(Path(f.name))
        assert result is None


def test_read_hash_ref():
    valid_hash = "a" * HASH_LENGTH

    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write(valid_hash)
        f.flush()

        result = read_ref(Path(f.name))
        assert isinstance(result, HashRef)
        assert result == valid_hash


def test_read_ref_invalid_format_raises_error():
    """Test that reading an invalid reference format raises ValueError."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("invalid reference content")
        f.flush()

        with raises(ValueError):
            read_ref(Path(f.name))


def test_read_ref_invalid_hash_length():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("abc123")  # Too short hash
        f.flush()

        with raises(ValueError):
            read_ref(Path(f.name))


def test_read_ref_invalid_hash_characters():
    invalid_hash = "g" * HASH_LENGTH  # 'g' is not a valid hex character

    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write(invalid_hash)
        f.flush()

        with raises(ValueError):
            read_ref(Path(f.name))


def test_write_hash_ref():
    hash_ref = HashRef("a" * HASH_LENGTH)

    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        write_ref(Path(f.name), hash_ref)

        with open(f.name, 'r') as read_f:
            content = read_f.read()
            assert content == hash_ref


def test_write_symbolic_ref():
    sym_ref = SymRef("refs/heads/main")

    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        write_ref(Path(f.name), sym_ref)

        with open(f.name, 'r') as read_f:
            content = read_f.read()
            assert content == "ref: refs/heads/main"


def test_write_invalid_ref_type_raises_error():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        with raises(ValueError):
            write_ref(Path(f.name), 123)  # Invalid type
