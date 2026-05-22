# .env and python-dotenv

LabTrust-Gym loads API keys from a `.env` file in the repo root (or from the environment). This requires the `python-dotenv` package in the **same** Python environment you use to run `labtrust`.

## Two Pythons, one dotenv

You may see `pip install python-dotenv` report "Requirement already satisfied" (for example in `miniconda3\lib\site-packages`) while `python -c "from dotenv import load_dotenv"` fails with `ModuleNotFoundError: No module named 'dotenv'`. That pattern means `pip` and `python` point at different environments, so `python-dotenv` is installed for one interpreter while you run another.

## Fix: install in the environment that runs `labtrust`

Use the **same** interpreter for both installing and running:

```powershell
# Install dotenv for the Python that runs when you type "python"
python -m pip install python-dotenv
```

You can also install or reinstall the project so its dependencies (including `python-dotenv`) land in the active environment:

```powershell
# From repo root, with your venv/conda env activated
pip install -e ".[llm_openai]"
```

Then confirm:

```powershell
python -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('.env')); import os; print('OPENAI_API_KEY set:', bool(os.environ.get('OPENAI_API_KEY')))"
```

You should see `OPENAI_API_KEY set: True` when `.env` exists in the current directory and contains `OPENAI_API_KEY=...`.
