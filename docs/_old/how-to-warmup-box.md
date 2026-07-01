# How to warmup a box

We've got an entrypoint/command that simplifies warmup of models for you.

1. Make sure that the config for the model exists in `configs/model/`
2. Run the warmup command using Hydra overrides:

```bash
uv run python -m gptnt.interactive.entrypoints.warmup_box model=<model_name>
```

It runs for 10 iterations by default, loading the full instructions and manuals that the model supports. It's also a good way to make sure that everything is working fine with the model setup.
