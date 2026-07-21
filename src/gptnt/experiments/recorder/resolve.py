from __future__ import annotations

from gptnt.experiments.ledger.base import Source
from gptnt.experiments.recorder.local import ExperimentPlayerRecorder


def _get_path_to_obj(obj: object) -> str:  # noqa: WPS110
    object_class = obj if isinstance(obj, type) else type(obj)
    return f"{object_class.__module__}.{object_class.__qualname__}"


def resolve_recorder(source: Source) -> str:
    """Using the source, get the target for the resolver."""
    if source is Source.wandb:
        from gptnt.experiments.recorder.wandb import WandbExperimentPlayerRecorder  # noqa: PLC0415

        return _get_path_to_obj(WandbExperimentPlayerRecorder)

    return _get_path_to_obj(ExperimentPlayerRecorder)
