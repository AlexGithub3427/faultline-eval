from datasets import load_dataset, DatasetDict
from unidiff import PatchSet
from typing import Literal
from pathlib import Path

LITE_REVISION = "6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2"
ROOT = Path(__file__).resolve().parents[2]
SPLITS_DIR = ROOT / "data" / "splits"

def load_lite() -> DatasetDict:
    return load_dataset("princeton-nlp/SWE-bench_Lite", revision=LITE_REVISION)

# returns list[gold_file, hunk count,lines_added_count, lines_removed_count]
def gold_file_shape(patch: str) -> list[tuple[str, int, int, int]]:
    files = []
    patch_data = PatchSet(patch)
    for patched_file in patch_data:
        files.append((patched_file.path, len(patched_file), patched_file.added, patched_file.removed))
    return files


def load_split(split: Literal["dev", "test"]) -> list[str]:
    if split not in ("dev", "test"):
        raise ValueError(f"unknown split {split!r}; expected 'dev' or 'test'")

    path = SPLITS_DIR / f"{split}.txt"
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]
