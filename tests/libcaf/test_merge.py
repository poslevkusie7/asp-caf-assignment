from libcaf.repository import Repository
from libcaf import Commit
from libcaf.plumbing import save_commit, hash_object
from libcaf.ref import HashRef
import libcaf.index
from datetime import datetime
from libcaf.merge import merge_content, FileLineSequence

# Helper to create a commit immediately
def create_commit(repo: Repository, parents: list[str], message: str) -> str:
    # create a file to ensure different tree hash if needed, or just reusing empty tree is fine
    # but to be safe and "real", let's update index with a file
    filename = f"file_{message}.txt"
    filepath = repo.working_dir / filename
    filepath.write_text(f"content for {message}")
    
    # Equivalent to "git add" - using the public repository API
    repo.update_index(filepath)
    
    # write the tree from index
    index_data = repo.read_index()
    tree_hash = libcaf.index.build_tree_from_index(index_data, repo.objects_dir())
    
    commit = Commit(tree_hash, "User", message, int(datetime.now().timestamp()), parents)
    save_commit(repo.objects_dir(), commit)
    return hash_object(commit)

def test_merge_base_linear(temp_repo: Repository) -> None:
    # A -> B -> C
    hash_a = create_commit(temp_repo, [], "A")
    hash_b = create_commit(temp_repo, [hash_a], "B")
    hash_c = create_commit(temp_repo, [hash_b], "C")
    
    assert temp_repo.merge_base(hash_a, hash_c) == hash_a
    assert temp_repo.merge_base(hash_b, hash_c) == hash_b
    assert temp_repo.merge_base(hash_a, hash_b) == hash_a
    assert temp_repo.merge_base(hash_b, hash_a) == hash_a

def test_merge_base_branching(temp_repo: Repository) -> None:
    # A -> B
    # |
    # +--> C
    hash_a = create_commit(temp_repo, [], "A")
    hash_b = create_commit(temp_repo, [hash_a], "B")
    hash_c = create_commit(temp_repo, [hash_a], "C")
    
    assert temp_repo.merge_base(hash_b, hash_c) == hash_a
    assert temp_repo.merge_base(hash_c, hash_b) == hash_a

def test_merge_base_diamond(temp_repo: Repository) -> None:
    # A -> B -> D
    # |    
    # +--> C -> D
    # 
    # Merge base of B and C is A.
    hash_a = create_commit(temp_repo, [], "A")
    hash_b = create_commit(temp_repo, [hash_a], "B")
    hash_c = create_commit(temp_repo, [hash_a], "C")
    hash_d = create_commit(temp_repo, [hash_b, hash_c], "D")
    
    # merge_base(B, C) should be A
    assert temp_repo.merge_base(hash_b, hash_c) == hash_a
    
    # merge_base(D, A) should be A
    assert temp_repo.merge_base(hash_d, hash_a) == hash_a
    
    # merge_base(D, B) should be B
    assert temp_repo.merge_base(hash_d, hash_b) == hash_b

def merge_content_helper(base_content: str, source_content: str, other_content: str, tmp_path) -> str:
    base = tmp_path / "base"
    source = tmp_path / "source"
    other = tmp_path / "other"
    base.write_text(base_content)
    source.write_text(source_content)
    other.write_text(other_content)
    return "".join(merge_content(base, source, other))

def test_merge_content_no_changes(tmp_path):
    base = "line1\nline2\n"
    assert merge_content_helper(base, base, base, tmp_path) == base

def test_merge_content_source_changes(tmp_path):
    base = "line1\nline2\n"
    source = "line1\nline2 modified\n"
    other = base
    assert merge_content_helper(base, source, other, tmp_path) == source

def test_merge_content_other_changes(tmp_path):
    base = "line1\nline2\n"
    source = base
    other = "line1\nline2 modified\n"
    assert merge_content_helper(base, source, other, tmp_path) == other

def test_merge_content_both_change_distinct_lines(tmp_path):
    base = "line1\nline2\nline3\n"
    source = "line1 modified\nline2\nline3\n"
    other = "line1\nline2\nline3 modified\n"
    expected = "line1 modified\nline2\nline3 modified\n"
    assert merge_content_helper(base, source, other, tmp_path) == expected

def test_merge_content_both_change_same_content(tmp_path):
    base = "line1\n"
    source = "line1 modified\n"
    other = "line1 modified\n"
    assert merge_content_helper(base, source, other, tmp_path) == source

def test_merge_content_conflict(tmp_path):
    base = "line1\n"
    source = "line1 source\n"
    other = "line1 other\n"
    expected = "<<<<<<< source\nline1 source\n=======\nline1 other\n>>>>>>> other\n"
    assert merge_content_helper(base, source, other, tmp_path) == expected

def test_merge_content_conflict_middle(tmp_path):
    base = "line1\nline2\nline3\n"
    source = "line1\nline2 source\nline3\n"
    other = "line1\nline2 other\nline3\n"
    expected = "line1\n<<<<<<< source\nline2 source\n=======\nline2 other\n>>>>>>> other\nline3\n"
    assert merge_content_helper(base, source, other, tmp_path) == expected

def test_merge_content_insertion_conflict(tmp_path):
    base = "line1\nline2\n"
    source = "line1\ninserted source\nline2\n"
    other = "line1\ninserted other\nline2\n"
    # Both inserting between line1 and line2
    expected = "line1\n<<<<<<< source\ninserted source\n=======\ninserted other\n>>>>>>> other\nline2\n"
    assert merge_content_helper(base, source, other, tmp_path) == expected


def test_merge_content_large_file(tmp_path):
    # Create a large file (> 2 pages, assuming 4KB pages, so > 8KB)
    # 10,000 lines of "line X\n" will be roughly 70-80KB
    num_lines = 10000
    base_content = "".join([f"line {i}\n" for i in range(num_lines)])
    
    # Introduce a change at end and beginning
    source_content = base_content.replace("line 0\n", "line 0 modified\n")
    other_content = base_content.replace(f"line {num_lines-1}\n", f"line {num_lines-1} modified\n")
    
    # Expected result should have both changes (no conflict)
    expected_content = source_content.replace(f"line {num_lines-1}\n", f"line {num_lines-1} modified\n")
    
    merged = merge_content_helper(base_content, source_content, other_content, tmp_path)
    assert merged == expected_content

def test_merge_content_empty_files(tmp_path):
    # Case 1: All empty
    assert merge_content_helper("", "", "", tmp_path) == ""
    
    # Case 2: Source adds content
    assert merge_content_helper("", "content\n", "", tmp_path) == "content\n"
    
    # Case 3: Other adds content
    assert merge_content_helper("", "", "content\n", tmp_path) == "content\n"
    
    # Case 4: Base has content, both deleted it
    assert merge_content_helper("content\n", "", "", tmp_path) == ""


def test_file_line_sequence_basic(tmp_path):
    f = tmp_path / "test_seq.txt"
    f.write_text("line1\nline2\nline3")
    
    with FileLineSequence(f) as seq:
        assert len(seq) == 3
        # Direct access
        assert seq[0] == "line1\n"
        assert seq[1] == "line2\n"
        assert seq[2] == "line3"
        # Negative indexing
        assert seq[-1] == "line3"
        assert seq[-2] == "line2\n"



def test_file_line_sequence_context_manager(tmp_path):
    f = tmp_path / "ctx.txt"
    f.write_text("foo\n")
    
    seq = FileLineSequence(f)
    # Access without context manager should raise because mmap is not open
    try:

        with seq as s:
            assert s is seq
            assert s[0] == "foo\n"
    finally:
        # Ensure it is closed if test fails inside block
        pass
    
    # After exit, access should fail
    import pytest
    with pytest.raises(ValueError): # mmap closed
        _ = seq[0]

def test_file_line_sequence_lazy_slicing(tmp_path):
    f = tmp_path / "lazy_slice.txt"
    # Write enough content so we can distinguish partial vs full scan
    lines = [f"line{i}\n" for i in range(10)]
    f.write_text("".join(lines))
    
    with FileLineSequence(f) as seq:
        # 1. Init should not scan
        assert seq._is_fully_scanned is False
        assert len(seq._offsets) <= 2 # 0 and maybe 1 depending on impl details, but definitely not 11
        
        # 2. Slice [0:2] should only scan up to 2
        slice_res = seq[0:2]
        assert slice_res == ["line0\n", "line1\n"]
        assert seq._is_fully_scanned is False
        assert len(seq._offsets) >= 3 # 0, len(l0), len(l0+l1)
# Verify lazy loading: Ensure we didn't scan too far ahead.
    # We allow < 11 to account for internal chunk reading buffer.
        assert len(seq._offsets) < 11
        
        # 3. Accessing beyond should trigger more scanning
        _ = seq[5]
        assert len(seq._offsets) >= 6
        assert seq._is_fully_scanned is False
        
        # 4. Full slice should scan all
        _ = seq[:]
        assert seq._is_fully_scanned is True
        assert len(seq) == 10

