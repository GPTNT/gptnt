import warnings

from pydantic.warnings import UnsupportedFieldAttributeWarning

# wandb uses pydantic models in a way pydantic dislikes. Silence the noise.
warnings.filterwarnings("ignore", category=UnsupportedFieldAttributeWarning)
