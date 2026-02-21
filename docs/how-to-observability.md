# How to observability

Traces, logs, and metrics all go through an OTEL collector, which forwards everything to [Logfire](https://logfire.pydantic.dev/).

The collector runs via Docker Compose (`otel-collector` service in `docker-compose.yml`). It listens on the standard OTLP ports (gRPC `4317`, HTTP `4318`) and also tails the KTANE Unity log file directly.

## `--limit-observability`

By default, `gptnt throw` runs with full instrumentation — FastAPI, FastStream, HTTPX, Redis, metrics, the lot. That's usually fine, but it can get noisy and adds overhead. You don't want this when you are running all the experiments because it can send 60M spans every 12 hours.

Pass `--limit-observability` to dial most of that back:

```bash
gptnt throw 4 claude45:8 --limit-observability
```

What it does:

- Disables FastAPI, FastStream, HTTPX, and Redis auto-instrumentation
- Disables metrics collection (it was causing some crashes sometimes, so we just get rid of it)
- Keeps pydantic-ai instrumentation on (in case we have any new errors)
- Sets `sampling.aggressive=true` on the resource, so the collector enables tail sampling and sets a minimum level (and more)

Under the hood it just injects a bunch of `OBSERVABILITY_*` env vars into the throw processes (see `_limit_observability_settings()` in [`src/gptnt/cli/throw.py`](../src/gptnt/cli/throw.py)). The env var definitions are in [`src/gptnt/common/instrumentation.py`](../src/gptnt/common/instrumentation.py).

## Send details KTANE logs to Logfire

The KTANE log tail sampling is controlled separately via `storage/otel-collector-config.yaml`. This is because the KTANE logs come from a file, so we can't just set them with the `OTEL_RESOURCE_ATTRIBUTES` env var like we do for the throw processes. Unfortunately/currently, if you want to change this, you have to edit the collector's config file.

Find the following in `storage/otel-collector-config.yaml`:

```yaml
resource:
  service.name: "ktane"
  sampling.aggressive: "true"
```

`sampling.aggressive: "true"` drops the noisy stuff and only keeps the important signals. Set it to `"false"` to get everything. **You'll need to restart the collector after changing this.**
