# victron-gx

Home Assistant integration for Victron GX devices.

## Development setup

Run the bootstrap script from the repository root (creates `.venv`, installs dependencies, and registers git hooks):

```bash
scripts/setup-dev.sh
```

Activate the virtual environment for interactive work:

```bash
source .venv/bin/activate
```

### Dev container

Opening this repository in a dev container runs `scripts/setup-dev.sh` automatically via `postCreateCommand`.

### Quality checks

Git commits run [pre-commit](https://pre-commit.com/) hooks (Ruff lint/format and pytest). Run them manually with:

```bash
.venv/bin/pre-commit run --all-files
```
