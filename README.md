# Reference: Gemini Enterprise App Backup & Restore Tool

A reference command-line interface (CLI) tool to backup and restore Gemini Enterprise App.



## Prerequisites

- Python 3.10 or higher.
- [uv](https://github.com/astral-sh/uv) or `pip`.
- Authentication:
  - Place a Service Account JSON key named `credentials.json` in the root directory (recommended), **OR**
  - Authenticate using Google Application Default Credentials: `gcloud auth application-default login`.
- Correct IAM permissions on the target GCP projects (e.g., `Discovery Engine Admin` or `Discovery Engine Editor`).

## Installation

We use `uv` to manage dependencies. To set up the virtual environment and install dependencies, run:

```bash
uv sync
```

Alternatively, you can run the tool directly using `uv run`, which will handle dependencies automatically:

```bash
uv run python backup_restore.py --help
```

## Usage

### 0. Interactive Mode (Recommended)

You can run the tool in interactive mode, which will guide you through the backup or restore process with prompts:

```bash
uv run python backup_restore.py -i
```

Or simply run it without any arguments:

```bash
uv run python backup_restore.py
```

It will automatically:
- Detect your default GCP Project ID.
- List all available Engines (Apps) in your project/location so you can select one by number.
- Guide you through all configuration options with sensible defaults.

### 1. Backup an App (Non-Interactive)

To backup an Engine and its assets and save the metadata locally:

```bash
uv run python backup_restore.py backup \
  --project <source_project_id> \
  --engine <engine_id> \
  --output-dir ./my-backup
```

### 2. Restore an App (Non-Interactive)

To restore an app from a local backup directory:

```bash
uv run python backup_restore.py restore \
  --backup-dir ./my-backup \
  --project <target_project_id>
```
