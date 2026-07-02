from typing import Annotated

from cyclopts import Parameter

PlayerOption = Annotated[
    str,
    Parameter(name="--player", help="Player config name (under configs/player/).", group="Player"),
]

ProviderOption = Annotated[
    str | None,
    Parameter(
        name="--provider",
        help="Provider config override (under configs/player/provider/).",
        group="Player",
    ),
]

DownloadOption = Annotated[
    bool,
    Parameter(
        name="--download",
        help="Download the dataset up-front before running (mainly for debugging).",
    ),
]

ThrowOption = Annotated[bool, Parameter(name="--throw", help="Actually execute the evaluation.")]

UploadOption = Annotated[
    bool, Parameter(name="--upload", help="Upload the evaluation results to Weave.")
]

LimitInstancesOption = Annotated[
    int | None,
    Parameter(
        name="--limit-instances", help="Limit the number of instances to evaluate (for debugging)."
    ),
]

AllowThinkingOption = Annotated[
    bool,
    Parameter(
        name="--allow-thinking",
        negative="--no-thinking",
        help="Enable reasoning/thinking mode for the model.",
    ),
]

StateRecognitionSplitOption = Annotated[
    str,
    Parameter(
        name="--state-split",
        help="State-recognition split to evaluate: state-change, solved, or strikes.",
    ),
]
