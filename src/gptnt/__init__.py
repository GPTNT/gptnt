import warnings

from pydantic.warnings import UnsupportedFieldAttributeWarning

# wandb uses pydantic models in a way pydantic dislikes; silence the noise.
warnings.filterwarnings("ignore", category=UnsupportedFieldAttributeWarning)
