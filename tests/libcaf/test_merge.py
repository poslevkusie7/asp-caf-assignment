from libcaf.repository import Repository
from libcaf import Commit
from libcaf.plumbing import save_commit, hash_object
from libcaf.ref import HashRef
from datetime import datetime

# Helper to create a commit immediately
def create_commit(repo: Repository, parents: list[str], message: str) -> str:
    # Use a dummy tree hash (valid format but pointing to nothing, which is fine for merge_base)
    dummy_tree = "0" * 40
    commit = Commit(dummy_tree, "User", message, int(datetime.now().timestamp()), parents)
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
