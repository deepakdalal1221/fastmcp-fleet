from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AuthSpec(BaseModel):
    type: str = "none"
    env: list[str] = Field(default_factory=list)


class ServerManifest(BaseModel):
    id: str
    name: str
    category: str
    description: str
    auth: AuthSpec
    transport: str = "streamable-http"
    port: int
    image: str
    version: str
    tools: list[str] = Field(default_factory=list)
    docs: str = ""
    maintainers: list[str] = Field(default_factory=list)
    status: str = "planned"


def _registry_dir() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parents[2], here.parents[3]):
        d = candidate / "registry" / "servers"
        if d.is_dir():
            return d
    raise FileNotFoundError("registry/servers directory not found")


def load_manifest(server_id: str, *, registry_dir: Path | None = None) -> ServerManifest:
    base = registry_dir or _registry_dir()
    path = base / f"{server_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"manifest not found for server '{server_id}': {path}")
    with path.open() as f:
        data = yaml.safe_load(f)
    return ServerManifest.model_validate(data)


def load_catalogue(*, registry_dir: Path | None = None) -> list[ServerManifest]:
    base = registry_dir or _registry_dir()
    manifests: list[ServerManifest] = []
    for path in sorted(base.glob("*.yaml")):
        with path.open() as f:
            data = yaml.safe_load(f)
        manifests.append(ServerManifest.model_validate(data))
    return manifests
