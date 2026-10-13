"""Generalization Benchmark V2 Package."""

from argus.investigation.benchmark.v2.tasks import (
    build_generalization_v2_tasks,
)
from argus.investigation.benchmark.v2.corpus import (
    InvestigationDocument,
    InvestigationCorpusRegistryV2,
    build_generalization_v2_corpus,
)

__all__ = [
    "build_generalization_v2_tasks",
    "InvestigationDocument",
    "InvestigationCorpusRegistryV2",
    "build_generalization_v2_corpus",
]
