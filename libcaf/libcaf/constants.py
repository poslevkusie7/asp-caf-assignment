"""Constants used throughout libcaf."""

from _libcaf import hash_length

DEFAULT_REPO_DIR = '.caf'
OBJECTS_SUBDIR = 'objects'
HEAD_FILE = 'HEAD'
MERGE_HEAD_FILE = 'MERGE_HEAD'
INDEX_FILE = 'index'
DEFAULT_BRANCH = 'main'
REFS_DIR = 'refs'
HEADS_DIR = 'heads'
TAGS_DIR = 'tags' 

HASH_LENGTH = hash_length()
HASH_CHARSET = '0123456789abcdef'
