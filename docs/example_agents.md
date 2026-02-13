# Example agents

Reference list of example agents in `examples/` with how to run them.

| Example | Description | Run command |
|---------|-------------|-------------|
| **minimal_random_policy_agent** | Minimal runnable agent: seeded random choice of NOOP or TICK; respects log_frozen. | `labtrust eval-agent --task throughput_sla --episodes 2 --agent "examples.minimal_random_policy_agent:MinimalRandomAgent" --out out.json` |
| **external_agent_demo** | Policy-aware trivial agent (NOOP or TICK only); SafeNoOpAgent or factory create_safe_noop_agent. | `labtrust eval-agent --task throughput_sla --episodes 2 --agent "examples.external_agent_demo:SafeNoOpAgent" --out out.json` |
| **scripted_ops_agent** | Standalone script: ScriptedOpsAgent (ops_0) with random runners; prints metrics. | `python examples/scripted_ops_agent.py` (requires `pip install -e ".[env]"`) |
| **scripted_runner_agent** | Standalone script: ScriptedOpsAgent + ScriptedRunnerAgent; ops and runners scripted. | `python examples/scripted_runner_agent.py` (requires `pip install -e ".[env]"`) |
| **llm_agent_mock_demo** | Standalone script: TaskB with LLMAgent(MockDeterministicBackend) and scripted runners. | `python examples/llm_agent_mock_demo.py` (requires `pip install -e ".[env]"`) |

For implementing your own agent and wiring it to `eval-agent`, see [Build your own agent](build_your_own_agent.md). Agents compatible with `eval-agent` can subclass **LabTrustAgentBase** (`labtrust_gym.baselines.agent_api`) for default implementations of optional methods (reset, explain_last_action, healthcheck, warm_up); you then override `act()` and optionally `contract_version`. The **LabTrustAgent** protocol is documented in the agent loader: `reset(seed, policy_summary, partner_id, timing_mode)`, `act(observation) -> int`, optional `explain_last_action() -> dict`.
