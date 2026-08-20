<div align='center'>

# GPTNT

_Can two AI agents talk each other through defusing a bomb?_

GPTNT is a benchmark for real-time collaboration between multimodal agents. Two AI agents play the
roles of _Defuser_ and _Expert_ in
[_Keep Talking and Nobody Explodes_ (KTANE)](https://keeptalkinggame.com). The Defuser sees the bomb,
the Expert reads the manual, and they must communicate to defuse it.

</div>

## Download

```bash
curl -fsSL \
  https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz |
  tar -xzf -

cd gptnt
mise install
mise run sync
```

Continue with [Get started](https://gptnt.github.io/docs/get-started/) for checksum verification,
prerequisites, and the first run.
