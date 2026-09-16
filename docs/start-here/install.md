---
title: Install GPTNT
---

# Install GPTNT

Depending on what you want to do, there's some different ways to install GPTNT.


1. If you want to run the benchmark, [download the latest release](#download-the-latest-release){data-preview}
1. If you want to reproduce a result or investigate a submission, [download a specific version](#download-a-specific-version)
1. If you are developing with GPTNT, you can [clone the repository](#clone-for-contribution-and-development){data-preview}

### Download the latest release


=== "With `mise` (recommended)"

    ```bash
    # 1. Download and extract the latest release
    curl -fsSL \
      https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz |
      tar -xzf -
    cd gptnt

    # 2. Install the toolchain
    mise install

    # 3. Install dependencies
    mise run sync  # (1)!
    ```

    1. Runs `uv sync --all-groups --all-extras` to install dependencies and extras, and then installs Playwright-managed Chromium for the manual. All tasks are defined in `mise.toml` so you can check them yourself.

=== "Without `mise`"

    ```bash
    # 1. Download and extract the latest release
    curl -fsSL \
      https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz |
      tar -xzf -
    cd gptnt

    # 2. Find out what tools we used from the `mise.toml` file and install them.

    # 3. Install dependencies
    uv sync --all-groups --all-extras
    uv playwright install chromium
    ```


The archive contains the source, benchmark inputs, and Git metadata used to identify the release.
You do not need a system Git executable to run the bundled benchmark. Do not remove the bundled
`.git` directory. GPTNT reads the release tag and protected-content baseline from it.


??? question "Is `mise` required?"
    During development, we use [mise-en-place](https://mise.jdx.dev) to manage the toolchain and secrets. It simplifies the installation of Python versions, uv versions, and other tool dependencies. It also manages environment variables and secrets for you. You can use it if you want, but it is not required.


??? tip "Verify the checksum"

    Download the archive and checksum **before extraction** to verify the release is not corrupted or tampered with. If you have already downloaded and extracted the archive, you can still verify the checksum by downloading the checksum file and running the command below.

    === "Linux"

        ```bash title="Download and verify the release"
        curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz
        curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz.sha256
        sha256sum --check gptnt.tar.gz.sha256
        tar -xzf gptnt.tar.gz
        ```

    === "macOS"

        ```bash title="Download and verify the release"
        curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz
        curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz.sha256
        shasum --algorithm 256 --check gptnt.tar.gz.sha256
        tar -xzf gptnt.tar.gz
        ```

    The archive extracts into `gptnt/`. Run `mise install` and `mise run sync` from that directory.

??? note "There's a ZIP archive if you want it"
    The release also publishes `gptnt.zip` and `gptnt.zip.sha256`. Download both, verify the
    checksum with the platform command above, and run `unzip gptnt.zip`. The ZIP contains the same
    checkout and bundled Git metadata as the tar archive.


<a name="download-a-specific-version"></a>
!!! info "Download a specific version"

    Replace `vX.Y.Z` with the release you want.

    ```bash
    curl -fsSLO https://github.com/GPTNT/gptnt/releases/download/vX.Y.Z/gptnt.tar.gz
    curl -fsSLO https://github.com/GPTNT/gptnt/releases/download/vX.Y.Z/gptnt.tar.gz.sha256
    sha256sum --check gptnt.tar.gz.sha256
    tar -xzf gptnt.tar.gz

    cd gptnt
    mise install
    mise run sync
    ```


### Clone for contribution and development

This is the recommended installation for developers. It uses the latest code on the selected branch rather than a published benchmark release. `mise` installs the required Python and `uv` versions, then runs the repository tasks. The `sync` task installs all dependency groups and extras, then installs Playwright-managed Chromium for manual preparation.

```bash title="Install from a Git checkout"
git clone https://github.com/GPTNT/gptnt.git
cd gptnt
mise install
mise run sync
```
