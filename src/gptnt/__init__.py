import warnings

from pydantic.warnings import UnsupportedFieldAttributeWarning

# This is because of wandb using pydantic models in a way pydantic doesn't like
warnings.filterwarnings("ignore", category=UnsupportedFieldAttributeWarning)
