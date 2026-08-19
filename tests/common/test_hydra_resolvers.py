from omegaconf import OmegaConf

from gptnt.common import hydra as hydra_config


def test_gptnt_config_resolvers() -> None:
    assert hydra_config is not None  # Import registers GPTNT's OmegaConf resolvers.
    config = OmegaConf.create(
        {
            "same": "${gptnt.eq:inner-monologue,inner-monologue}",
            "different": "${gptnt.eq:inner-monologue,thinking-out-loud}",
            "budget": "${gptnt.floor_mul:1001,0.85}",
        }
    )

    OmegaConf.resolve(config)

    assert config.same is True
    assert config.different is False
    assert config.budget == 850
