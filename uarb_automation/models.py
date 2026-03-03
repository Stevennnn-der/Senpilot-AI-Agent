from dataclasses import dataclass
from typing import Dict, List

@dataclass
class MatterResult:
    zip_path: str
    downloaded_files: List[str]
    counts_per_tab: Dict[str, int]
    total_count: int
    metadata: Dict[str, str]