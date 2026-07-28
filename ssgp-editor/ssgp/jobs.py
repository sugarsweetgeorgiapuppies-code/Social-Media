"""In-memory job registry (thread-safe). No external services required."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Job:
    id: str
    status: str = "queued"            # queued | processing | succeeded | failed
    progress: int = 0                 # 0..100
    stage: str = "queued"             # human-readable current stage
    url: Optional[str] = None         # finished mp4 url when succeeded
    error: Optional[str] = None
    sources: List[str] = field(default_factory=list)   # urls or "upload:<name>"
    instructions: str = ""
    notes: List[str] = field(default_factory=list)      # how instructions were read
    options: Dict[str, Any] = field(default_factory=dict)
    applied: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def public(self) -> Dict[str, Any]:
        """The Creatomate-style status payload for GET /render/{id}."""
        return {
            "id": self.id,
            "status": self.status,
            "url": self.url,
            "error": self.error,
            "progress": self.progress,
            "stage": self.stage,
            "notes": self.notes,
            "applied": self.applied,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, **kwargs) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, **kwargs)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            job.updated_at = time.time()

    def all(self) -> List[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
