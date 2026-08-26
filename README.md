<div align='center'>

# GPTNT

_Can two AI agents talk each other through defusing a bomb?_

GPTNT is a benchmark for real-time collaboration between multimodal agents. Two AI agents play the
roles of _Defuser_ and _Expert_ in
[_Keep Talking and Nobody Explodes_ (KTANE)](https://keeptalkinggame.com). The Defuser sees the bomb,
the Expert reads the manual, and they must communicate to defuse it.

</div>

This benchmark uses the real game and the official manual. We have done as much as possible to make everything easy to use and run, and have put all the information to help you get started on our [documentation site](https://gptnt.github.io/docs/).



## Download

```bash
curl -fsSL \
  https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz |
  tar -xzf -

cd gptnt
mise install
mise run sync
```

Continue with [Install and check GPTNT](https://gptnt.github.io/docs/start-here/install-and-check/)
for checksum verification, prerequisites, and the first run.
