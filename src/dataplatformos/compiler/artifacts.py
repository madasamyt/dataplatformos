"""Generated artifact helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GeneratedArtifact:
    relative_path: str
    content: str
    kind: str = "file"

    def write(self, output_dir: Path) -> Path:
        path = output_dir / self.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.content, encoding="utf-8")
        return path


@dataclass
class CompileResult:
    artifacts: list[GeneratedArtifact] = field(default_factory=list)
    output_dir: Path | None = None

    def add(self, artifact: GeneratedArtifact) -> None:
        self.artifacts.append(artifact)

    def write_all(self, output_dir: Path) -> list[Path]:
        self.output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        return [a.write(output_dir) for a in self.artifacts]
