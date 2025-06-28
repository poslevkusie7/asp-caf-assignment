from pathlib import Path
from typing import Optional

from .constants import HASH_CHARSET, HASH_LENGTH


class HashRef(str):
    pass


class SymRef(str):
    def branch_name(self) -> str:
        """Extract the branch name from a symbolic reference."""
        return self.split('/')[-1] if '/' in self else self


Ref = HashRef | SymRef | str


def read_ref(ref_file: Path) -> Optional[Ref]:
    with ref_file.open() as f:
        content = f.read().strip()
        if content.startswith('ref:'):
            return SymRef(content.split(': ')[-1])
        elif not content:
            return None
        elif len(content) == HASH_LENGTH and all(c in HASH_CHARSET for c in content):
            return HashRef(content)
        else:
            raise ValueError(f'Invalid reference format in ref file {ref_file}!')


def write_ref(ref_file: Path, ref: Ref) -> None:
    with ref_file.open('w') as f:
        match ref:
            case HashRef():
                f.write(ref)
            case SymRef(ref):
                f.write(f"ref: {ref}")
            case _:
                raise ValueError(f"Invalid reference type: {type(ref)}")
