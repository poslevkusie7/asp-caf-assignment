from libcaf.repository import Repository, RepositoryError
from libcaf import Commit
from libcaf.plumbing import save_commit, hash_object
from libcaf.ref import HashRef, SymRef, write_ref
import libcaf.index
from datetime import datetime
from libcaf.merge import merge_content, FileLineSequence


# Helper to create a commit immediately and update HEAD

def create_commit(repo: Repository, parents: list[str], message: str, files_to_add: list[str] = None) -> str:
    # default: create a unique file to ensure different tree hash if no specific files given
    if files_to_add is None:
        filename = f"file_{message}.txt"
        filepath = repo.working_dir / filename
        filepath.write_text(f"content for {message}")
        repo.update_index(filepath)
    else:
        # If files_to_add provided, we assume index is already prepared or we just add these extra unique markers
        for fname in files_to_add:
            filepath = repo.working_dir / fname
            if not filepath.exists():
                filepath.write_text(f"content for {fname} in {message}")
            repo.update_index(filepath)
    
    # write the tree from index
    index_data = repo.read_index()
    tree_hash = libcaf.index.build_tree_from_index(index_data, repo.objects_dir())
    
    commit = Commit(tree_hash, "User", message, int(datetime.now().timestamp()), parents)
    commit_hash = hash_object(commit)
    save_commit(repo.objects_dir(), commit)
    
    # Update HEAD
    head_ref = repo.head_ref()
    if isinstance(head_ref, SymRef):
        ref_path_in_refs = str(head_ref)
        if ref_path_in_refs.startswith("refs/"):
             ref_path_in_refs = ref_path_in_refs[5:] # strip "refs/"
             
        repo.update_ref(ref_path_in_refs, HashRef(commit_hash))
    else:
        # Detached HEAD, just write to HEAD file
        write_ref(repo.head_file(), HashRef(commit_hash))
        
    return commit_hash


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
    
    # Create branches for B and C to avoid detached HEAD commit hell
    temp_repo.add_branch("branch_b")
    temp_repo.checkout("branch_b")
    hash_b = create_commit(temp_repo, [hash_a], "B")
    
    temp_repo.checkout(hash_a)
    temp_repo.add_branch("branch_c")
    temp_repo.checkout("branch_c")
    hash_c = create_commit(temp_repo, [hash_a], "C")
    
    assert temp_repo.merge_base(hash_b, hash_c) == hash_a
    assert temp_repo.merge_base(hash_c, hash_b) == hash_a

def test_merge_base_diamond(temp_repo: Repository) -> None:
    # A -> B -> D
    # |    
    # +--> C -> D
    hash_a = create_commit(temp_repo, [], "A")
    
    temp_repo.add_branch("branch_b")
    temp_repo.checkout("branch_b")
    hash_b = create_commit(temp_repo, [hash_a], "B")
    
    temp_repo.checkout(hash_a)
    temp_repo.add_branch("branch_c")
    temp_repo.checkout("branch_c")
    hash_c = create_commit(temp_repo, [hash_a], "C")
    
    # D merges B and C
    temp_repo.checkout("branch_b")
    # Manually create D with two parents
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
    # After exit, access should fail
    try:
        _ = seq[0]
        assert False, "Should have raised ValueError"
    except ValueError:
        pass # Expected behavior

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


    


def test_merge_not_clean_workdir(temp_repo: Repository):
    # Setup: create a commit
    create_commit(temp_repo, [], "initial")
    
     # Dirty workdir
    (temp_repo.working_dir / "dirty_file").write_text("dirty")
    
    try:
        temp_repo.merge("some_ref")
        assert False, "Should have raised RepositoryError"
    except RepositoryError as e:
        assert "Working directory is not clean" in str(e)

def test_merge_fast_forward(temp_repo: Repository):
    # A -> B
    hash_a = create_commit(temp_repo, [], "A")
    hash_b = create_commit(temp_repo, [hash_a], "B")
    
    # Move HEAD back to A
    temp_repo.checkout(hash_a)
    
    # Merge B
    temp_repo.merge(hash_b)
    
    assert temp_repo.head_commit() == hash_b
    assert (temp_repo.working_dir / "file_B.txt").exists()


def test_merge_clean_3way_modified(temp_repo: Repository):
    # A -> B (mod file1)
    # |
    # +--> C (mod file2)
    
    # A
    f1 = temp_repo.working_dir / "file1.txt"
    f2 = temp_repo.working_dir / "file2.txt"
    f1.write_text("content1")
    f2.write_text("content2")
    temp_repo.update_index(f1)
    temp_repo.update_index(f2)
    
    hash_a = create_commit(temp_repo, [], "A")

    # B (mod file1)
    f1.write_text("content1 modified")
    temp_repo.update_index(f1)
    hash_b = create_commit(temp_repo, [hash_a], "B")

    # C (mod file2) - use branch
    temp_repo.checkout(hash_a)
    temp_repo.add_branch("feature")
    temp_repo.checkout("feature")
    
    f2.write_text("content2 modified")
    temp_repo.update_index(f2)
    # create_commit handles HEAD update for branch "feature"
    hash_c = create_commit(temp_repo, [hash_a], "C")
    
    # Merge C into B (checkout B first)
    
    temp_repo.checkout(hash_b) 
    
    temp_repo.merge(hash_c)
    
    # Check both mods present
    assert (temp_repo.working_dir / "file1.txt").read_text() == "content1 modified"
    assert (temp_repo.working_dir / "file2.txt").read_text() == "content2 modified"
    
    # Check MERGE_HEAD
    assert (temp_repo.repo_path() / "MERGE_HEAD").exists()
    assert (temp_repo.repo_path() / "MERGE_HEAD").read_text().strip() == hash_c

def test_merge_clean_3way_deleted(temp_repo: Repository):
    # A (file1) -> B (clean file1)
    # |
    # +--> C (delete file1)
    
    # A
    f1 = temp_repo.working_dir / "file1.txt"
    f1.write_text("content1")
    temp_repo.update_index(f1)
    hash_a = create_commit(temp_repo, [], "A")
    
    # B
    hash_b = create_commit(temp_repo, [hash_a], "B") 
    
    # C
    temp_repo.checkout(hash_a)
    temp_repo.add_branch("feature_del")
    temp_repo.checkout("feature_del")
    

    # C: Delete file1 and commit using helper
    temp_repo.remove_from_index("file1.txt")
    if (temp_repo.working_dir / "file1.txt").exists():
        (temp_repo.working_dir / "file1.txt").unlink()

    # Commit the deletion. Passing [] ensures no new files are auto-created.        
    hash_c = create_commit(temp_repo, [hash_a], "C", files_to_add=[])

    # Merge C into B
    temp_repo.checkout(hash_b)
    temp_repo.merge(hash_c)
    
    assert not (temp_repo.working_dir / "file1.txt").exists()

def test_merge_conflict(temp_repo: Repository):
    # A (file1=content) -> B (file1=contentB)
    # |
    # +--> C (file1=contentC)
    
    f1 = temp_repo.working_dir / "file1.txt"
    f1.write_text("content")
    temp_repo.update_index(f1)
    hash_a = create_commit(temp_repo, [], "A")
    
    # B
    f1.write_text("contentB")
    temp_repo.update_index(f1)
    hash_b = create_commit(temp_repo, [hash_a], "B")
    
    # C
    temp_repo.checkout(hash_a)
    temp_repo.add_branch("feature_conflict")
    temp_repo.checkout("feature_conflict")
    
    f1.write_text("contentC")
    temp_repo.update_index(f1)
    hash_c = create_commit(temp_repo, [hash_a], "C")
    
    # Merge C into B
    temp_repo.checkout(hash_b)
    temp_repo.merge(hash_c)
    
    content = f1.read_text()
    assert "<<<<<<< HEAD" in content
    assert "contentB" in content
    assert "=======" in content
    assert "contentC" in content
    assert ">>>>>>>" in content
