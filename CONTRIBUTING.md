# Contributing to Atlas Agents

Thank you for improving the examples that accompany *Hands-on AI Agents*.
Focused changes are easiest to review, especially when they affect one chapter
or one shared component.

## Set up a development environment

Atlas Agents supports Python 3.10 and newer. Create a virtual environment before
installing dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` only when an example needs a provider. Never
commit API keys, generated credentials, or populated `.env` files.

## Run offline checks

Changes should pass the checks that do not require network access or API keys:

```bash
python -m compileall -q .
python -m unittest discover -v
```

Run the changed example directly when it has an offline or dry-run path. If a
check needs a paid provider, describe the manual validation in the pull request
instead of placing it in the default test suite.

## Keep pull requests focused

1. Create a branch from the latest `main`.
2. Limit the change to one bug, chapter, or documentation concern.
3. Add deterministic tests for shared behavior when practical.
4. Document new dependencies and environment variables in the example's module
   docstring.
5. Include the commands you ran in the pull request description.

Examples are teaching material. Prefer explicit control flow and clear failure
messages over abstractions that hide the concept being demonstrated.

## Report security issues carefully

Do not include live credentials or sensitive production data in an issue. For a
security-sensitive bug, describe the smallest safe reproduction and the trust
boundary it crosses.
