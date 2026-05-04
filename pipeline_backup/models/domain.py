from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

class ReviewDecision(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"

class ModuleStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class Domain:
    name: str
    description: str
    packages: List[str]
    files: List[str]
    estimated_complexity: str  # low / medium / high

@dataclass
class WikiPage:
    filename: str
    title: str
    domain: str
    content: Optional[str] = None
    review_decision: Optional[ReviewDecision] = None
    review_score: float = 0.0
    review_issues: List[str] = field(default_factory=list)
    attempts: int = 0

@dataclass
class ModulePlan:
    module_name: str
    source_path: str
    output_path: str
    domains: List[Domain] = field(default_factory=list)
    wiki_pages: List[WikiPage] = field(default_factory=list)
    status: ModuleStatus = ModuleStatus.PENDING
