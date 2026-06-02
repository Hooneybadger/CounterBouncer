from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Workload:
    suite: str
    name: str
    input: str
    command: list[str]
    cwd: str
    version: str
    outcome_parser: object
    accepted_returncodes: list[int] = field(default_factory=lambda: [0])
    attach_pid: int | None = None
    metadata: dict = field(default_factory=dict)
