# GPTNT

## How to run things

We've tried to make it easy to get started with this project so that _ItJustWorks™_. We have tests, formatters, linters, CI, and more to make sure that everything is working as expected. That said, if something doesn't work, we'd like to know! Please open an issue on the repository.

### How is the codebase structured?

**This codebase is structured as a monorepo**: with multiple packages that work together to provide the functionality of the project, and yet are isolated enough to be worked on independently. The main package, found in `src/gptnt`, is the primary entrypoint for the entire project and uses all the other packages together.

We use [uv](https://docs.astral.sh/uv/) to manage the project and its dependencies, and use [uv's workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) to keep it all together.

### Prerequisites

We've tried to keep system/external dependencies to a minimum to facilitate _ItJustWorks™_. Here's what you need:

- [uv](https://docs.astral.sh/uv/)
- Python 3.12 (at least)

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

**To install everything**, you can run the following:

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
<summary><b>How to invoke the project</b></summary>

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

### How to verify that everything is working

Things happen and things break. Development is done using tests to verify that each piece works both in isolation and together. We recommend that you **run the tests first when using a new machine/node.**

The various tests are a good way of looking how different pieces were implemented and are used. While coverage is not 100%, use tests with breakpoints to verify things are working as expected. **If you contribute new code, please add tests to ensure that it works as expected.** You can find all the tests in the `tests/` folder.

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

<details>
<summary><b>What test suite is used?</b></summary>

We use [pytest](https://docs.pytest.org/en/stable/) and [pytest-cases](https://smarie.github.io/python-pytest-cases/). You can find all the packages used for testing in the `pyproject.toml`, under `dependency_groups`.

</details>

### How to run the code quality tools

To maintain consistency throughout the codebase, we use several linters and formatters. There are three ways to run these tools: locally using the command-line, within your IDE, or through the CI.

> [!CAUTION]
> I think I've covered everything but YMMV. This section might get tweaked a bit as we figure out what works best for everyone.

<details>
<summary><b>What are we using?</b></summary>

- [EditorConfig](https://editorconfig.org/), for maintaining consistent coding styles between different editors and IDEs
- [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, set as strict as possible
- [wemake-python-styleguide](https://wemake-python-styleguide.readthedocs.io/en/latest/) for additional opinionated linting
- [basedpyright](https://docs.basedpyright.com/latest/), for type-checking and improving the developer experience
- [pre-commit](https://pre-commit.com/), with many hooks to ensure nothing gets committed that shouldn't
- [`docformatter`](https://github.com/PyCQA/docformatter), for formatting docstrings
- [Prettier](https://prettier.io/), for formatting common front-end files (e.g., Markdown, JavaScript, CSS, etc.)
- [ShellCheck](https://www.shellcheck.net/), for linting shell scripts
- [shfmt](https://github.com/mvdan/sh), for formatting shell scripts

Additionally, **we enforce [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/)** through pre-commit hooks.

</details>

<details>
<summary><b>How to setup your repository to minimise CI pain?</b></summary>

After you first clone the repository, you should probably want to make sure that the CI isn't too harsh.

> [!IMPORTANT]
> You must install pre-commit's hooks into it. This is a one-time setup and must be done after cloning the repository.
>
> ```bash
> uv run pre-commit install
> ```

</details>

<details>
<summary><b>How to run things from the command line</b></summary>

It is possible to run all the tools from the command line. There's a few but here is how you do each.

> [!IMPORTANT]
> You must install pre-commit's hooks into it. This is a one-time setup and must be done after cloning the repository.
>
> ```bash
> uv run pre-commit install
> ```

- **pre-commit**

  ```bash
  uv run pre-commit run -a
  ```

- **wemake-python-styleguide**

  ```bash
  uv run flake8
  ```

- **basedpyright**

  ```bash
  uv run basedpyright
  ```

</details>

<details>

<summary><b>Recommended VSCode defaults to make things automatic</b></summary>

Many of the tools used are integrated with VSCode. To help you get started with making sure it's all working, we've included some recommended settings and extensions.

You can find the recommended extensions in the `.vscode/extensions.json` file. You can also find the settings in the `.vscode/settings.recommended.json` file.

Copy the settings from that file into your `.vscode/settings.json` file, and that will enable things. Ensure that you have installed the recommended extensions too. Importantly, if you are using basedpyright too, ensure you have disabled the Pylance extension.

</details>

> [!IMPORTANT]
> The CI has not yet been set up.

## License

## Citation
