# Plugin SDK (v1.0)

Adapters implement compile-time Protocols and return `GeneratedArtifact` lists.

## Core Protocols

```python
class SourceConnector(Protocol):
    def compile(self, project: Project) -> list[GeneratedArtifact]: ...

class TransformEngine(Protocol):
    def compile(self, project: Project) -> list[GeneratedArtifact]: ...

class QualityEngine(Protocol):
    def compile(self, project: Project) -> list[GeneratedArtifact]: ...
```

## Shipped (OSS defaults)

| Adapter | Module |
|---------|--------|
| Meltano | `dataplatformos.adapters.source.meltano` |
| Debezium | `dataplatformos.adapters.source.debezium` |
| Flink | `dataplatformos.adapters.transform.flink` |
| ML | `dataplatformos.adapters.transform.ml` |
| Deequ | `dataplatformos.adapters.quality.deequ` |
| Great Expectations | `dataplatformos.adapters.quality.great_expectations` |

## Commercial contrib (optional)

| Adapter | Module |
|---------|--------|
| Estuary | `contrib.commercial.estuary` |
| Dremio catalog | `contrib.commercial.dremio_catalog` |

Do not add commercial SDKs to the default `pip install dataplatformos` dependency set.

## Adding an adapter

1. Implement `compile(project) -> list[GeneratedArtifact]`
2. Register the call in `dataplatformos.compiler.compile.compile_project`
3. Add a fixture under `tests/` and an example under `examples/` when possible
