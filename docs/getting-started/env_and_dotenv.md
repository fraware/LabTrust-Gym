# .env and python-dotenv

LabTrust-Gym loads API keys from a `.env` file in the repo root (or from the environment). This requires the `python-dotenv` package in the **same** Python environment you use to run `labtrust`.

## Two Pythons, one dotenv

If you see:

- `pip install python-dotenv` reports "Requirement already satisfied" (e.g. in `miniconda3\lib\site-packages`)
- but `python -c "from dotenv import load_dotenv"` fails with `ModuleNotFoundError: No module named 'dotenv'`

then `pip` and `python` are using different environments. `python-dotenv` is installed for one interpreter but you are running another.

## Fix: install in the environment that runs `labtrust`

Use the **same** interpreter for both installing and running:

```powershell
# Install dotenv for the Python that runs when you type "python"
python -m pip install python-dotenv
```

Or install/reinstall the project so its dependencies (including `python-dotenv`) are in the active environment:

```powershell
# From repo root, with your venv/conda env activated
pip install -e ".[llm_openai]"
```

Then confirm:

```powershell
python -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('.env')); import os; print('OPENAI_API_KEY set:', bool(os.environ.get('OPENAI_API_KEY')))"
```

You should see `OPENAI_API_KEY set: True` when `.env` exists in the current directory and contains `OPENAI_API_KEY=...`.
