<div align='center'>

# GPTNT

_Can two AI agents talk each other through defusing a bomb?_

Two AI agents must play the roles of _Defuser_ and _Expert_ in [_Keep Talking and Nobody Explodes_ (KTANE)](https://keeptalkinggame.com). The Defuser sees the bomb, the Expert reads the manual, and they must communicate in real-time to defuse it.

</div>

## Links

- [Website](https://gptnt.github.io)
- [Paper](https://arxiv.org/abs/2606.28514)
- [Leaderboard](https://gptnt.github.io)
- [Documentation](https://gptnt.github.io/docs/)

## Summary

GPTNT is an AI benchmark built on **KTANE** ("Keep Talking and Nobody Explodes"): a co-op bomb-defusal game where a _Defuser_ who can see the bomb and an _Expert_ who can read the manual must talk to each other to defuse it. Here, the players are AI models. You run **experiments** that pair models against bombs and record how well they do. The job of this repo is to generate those experiments, run them, and collect the results.

> [!NOTE]
> Creating an asynchronous, real-time, multi-agent benchmark is not trivial. We've tried to make the process of running things as simple and clear as possible to ensure that no logs or information is lost in the async hell that can happen. You can find more information about how to get started and run the benchmark on the documentation site: [https://gptnt.github.io/docs/](https://gptnt.github.io/docs/).

## Citation

```bibtex
@misc{gptnt,
      title={GPTNT: Benchmarking Real-Time Collaboration Between Multimodal Agents on Keep Talking And Nobody Explodes},
      author={Amit Parekh and Sabrina McCallum and Kareem Al-Hasan and Malvina Nikandrou and Alessandro Suglia and Ioannis Konstas},
      year={2026},
      eprint={2606.28514},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2606.28514},
}
```

## License

This benchmark is licensed under the terms of the license found in [LICENSE](LICENSE).
