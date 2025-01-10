# GPTNT

## How to run things


### Prerequisites

We've tried to keep system/external dependencies to a minimum, but some things can't be helped.

- [uv](https://docs.astral.sh/uv/)
- Python 3.12


<details>
<summary><b>Optional way to simplify tool installation</b></summary>

You might want to use something like [mise-en-place](https://mise.jdx.dev/getting-started.html) to manage and install tools. For example, this is how you get setup with it:

```bash
mise use python@3.12 uv@latest
uv sync --all-groups
```

Note that we won't be helping with `mise` or any other tooling. We're just showing you how to use it.

</details>




### Installing the project

This project is managed with [uv](https://docs.astral.sh/uv/), and specifically we are using workspaces. You can also [use it to install Python](https://docs.astral.sh/uv/guides/install-python/) if you want.

To quickly install everything and get up and running, you can run the following:

```bash
uv sync --all-groups
```


<!-- <details>
<summary><b>What if you use <code>requirements.txt</code>?</b></summary>

Can't help you there.

</details>

<details>
<summary><b>How I install dependencies on every machine</b></summary>

I literally just run the following on the machines I use. I don't use Windows though so I can't help you there.

```bash
mise use python@3.11 pdm@latest
pdm install
```
</details> -->


<details>
<summary><b>How to invoke the package</b></summary>

The quickest way to make sure you're all setup is to run either of the following:

- If you know you've got a venv activated or something:
    ```bash
    python -m gptnt
    ```

- If you're using uv instead of activating the venv:
    ```bash
    uv run python -m gptnt
    ```

</details>




### How to check it works

Things happen and things break. Development is done using tests to verify that each piece works both in isolation and together. We recommend running the tests first when using a new machine/node to run the code.

You can find all the tests in the `tests/` folder. The various tests are a good way of looking how different pieces were implemented and are used. While coverage is not 100%, use tests with breakpoints to verify things are working as expected.

<details>
<summary><b>How to make sure all tests can be loaded without errors</b></summary>

```bash
uv run pytest --collect-only
```

This is also useful for just making sure things installed correctly and that all tests can be found.

</details>

<details>
<summary><b>How to run all the tests</b></summary>

```bash
uv run pytest
```

The CI for this project runs _in the exact same way_.

Check out [pytest-xdist](https://github.com/pytest-dev/pytest-xdist) if you want to know more about running tests in parallel, or just throw ` -n auto` on the end of the above commands. It makes it go faster by using multiple cores.

</details>

### How to find code and develop

To reduce the complexity of the repository, we have split the code into multiple packages (in `packages/`) and use [uv's workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) to keep it all together. If you only want to work on a certain part, you can do.

The main package, found in `src/gptnt`, is the primary entrypoint for the entire project and uses all the other packages together.

### How to run linters/formatters

> [!WARNING]
> This section is currently being written. Need a day or so

1. List the tools
2. How to run things from the command line
3. How to run things from the command line WITH mise tasks
4. How to run things from VSCode automatically


There are several linters and formatters, all working together to maintain consistency across the codebase. This is what we use:

- EditorConfig
- ruff
- wemake-python-styleguide
- basedpyright (used in place of Pylance/Pyright/mypy)
- pre-commit (with many hooks)
- conventional-commits (enforced through pre-commit hooks)

> [!NOTE]
> The CI for this project runs _in the exact same way_.


<details>
<summary><b>pre-commit</b></summary>

> [!IMPORTANT]
> You must install pre-commit's hooks into it. This is a one-time setup and must be done after cloning the repository.
>  ```bash
>  uv run pre-commit install
>  ```

Run the formatter (and ruff's linter) on everything:

```bash
uv run pre-commit run -a
```

</details>

<details>
<summary><b>wemake-python-styleguide</b></summary>

```bash
uv run flake8
```

</details>

<details>
<summary><b>basedpyright</b></summary>

```bash
uv run basedpyright
```

</details>




## License


## Citation
