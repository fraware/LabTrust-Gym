# Build your own agent

This page gives a 5–10 minute path from install to running a benchmark with your own agent.

## Steps

1. **Install** the package with env and plots:
   ```bash
   pip install labtrust-gym[env,plots]
   ```

2. **Verify** the environment:
   ```bash
   labtrust quick-eval
   ```
   You should see a markdown summary and logs under `./labtrust_runs/`.

3. **Implement an agent.** Your agent must provide an interface compatible with the runner: e.g. a class with `act(obs, agent_id)` returning an action index and optional info dict. Use `examples/external_agent_demo.py` in the repository as a template (module path `examples.external_agent_demo`, class `MyAgent`).

4. **Run a benchmark** with your agent:
   ```bash
   labtrust eval-agent --agent 'your_module:YourAgent' --task throughput_sla --episodes 2 --out results.json
   ```
   Example with the shipped external demo:
   ```bash
   labtrust eval-agent --agent 'examples.external_agent_demo:MyAgent' --task throughput_sla --episodes 2 --out out.json
   ```

5. **Inspect** `results.json` (or `out.json`): episode metrics, rewards, violations, and run metadata.

For more example agents (scripted, random, LLM mock) see `examples/` and [Example experiments](example_experiments.md). For the full API and observation/action spaces, see [PettingZoo API](pettingzoo_api.md) and [Benchmarks](benchmarks.md).
