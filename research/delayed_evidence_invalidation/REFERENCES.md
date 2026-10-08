# Prior-art and standards boundary

This file records sources that constrain novelty and benchmark design. It is not a claim that every source directly studies delayed evidence invalidation in autonomous laboratories.

## Autonomous laboratories and scientific-agent assurance

1. Canty, R. B.; Abolhasani, M. **The past, present and future of self-driving laboratories.** *Nature Reviews Chemistry* 10, 523–537 (2026). DOI: 10.1038/s41570-026-00847-2.  
   Relevance: scalability, generalizability, and provenance-complete experimentation as interdependent SDL requirements.

2. Chen, L.; Li, X.; Lin, Q.; et al. **Self-driving laboratories need an autonomy safety harness.** *Nature Synthesis* (2026). DOI: 10.1038/s44160-026-01120-6.  
   Relevance: AI intent, executable experiments, monitored actions, and trustworthy downstream evidence.

3. Yin, X.; Du, M.; Prince, M. H.; Cherukara, M. J. **Artifact-centered Claim-aware Observability for Autonomous Scientific Agents.** arXiv:2608.18312 (2026).  
   Relevance: claim-aware artifact lineage; prevents this study from claiming generic claim/evidence provenance as novel.

4. Bi, J.; Pinilla, S.; Zhu, C. **Certifying when decision-time information justifies adaptive experimentation.** arXiv:2607.27651 (2026).  
   Relevance: authorization is a distinct layer in adaptive science; prevents conflation of recovery with initial authorization.

5. Alnasir, J. J. **AI-Driven Scientific Computing Workflows: A Systems Review of Orchestration, Execution, Reproducibility and Provenance.** arXiv:2609.21162 (2026).  
   Relevance: identifies state-aware recovery, model-mediated decision provenance, and reproducible adaptive execution as open systems problems.

## Metrology and quality control

6. National Institute of Standards and Technology. **Measurement Assurance Programs / Calibration Policies** and **Measurement Assurance Basics**.  
   Relevance: periodic check standards, uncertainty estimation, statistical control, and continuous monitoring of measurement-process quality.

7. ASTM D6299-26. **Standard Practice for Applying Statistical Quality Assurance and Control Charting Techniques to Evaluate Analytical Measurement System Performance.**  
   Relevance: ongoing monitoring of precision/bias and analytical measurement system state of control.

8. ASTM E3500-25. **Standard Practice for Quality Control of Routine Testing in a Laboratory.**  
   Relevance: control samples, drift detection, out-of-control action plans, and acceptance/evaluation of sample results.

## Robust adaptive optimization and inference

9. Ezzerg, A.; Bogunovic, I.; Knoblauch, J. **Robust Bayesian Optimisation with Unbounded Corruptions.** ICML 2026, PMLR 306:28528–28565.  
   Relevance: strong comparator for acquisition robustness under corrupted observations; robust acquisition does not itself specify scientific invalidation semantics.

10. Adaptive-experiment and sequential-inference literature reviewed in:  
    **The Blessings and Curses of Adaptivity in Sequential Experiments** (Annual Review of Statistics and Its Application).  
    Relevance: adaptively collected data require explicit inferential treatment; later observations are not automatically equivalent to a fixed-design sample.

## Unlearning and downstream influence

11. Bourtoule, L.; et al. **Machine Unlearning.** arXiv:1912.03817.  
    Relevance: data influence persists in trained models after storage deletion; retraining/structured recovery baselines.

12. Ye, Z.; Wang, R.; Wang, X.; Liu, X.; Li, S.; Hajiesmaili, M. **Unlearning Offline Stochastic Multi-Armed Bandits.** arXiv:2605.00638 (2026).  
    Relevance: unlearning in sequential decision-making and rollback/utility trade-offs. The present study must not claim that unlearning in sequential decision systems is new.

13. Ding, Z.; Huang, J.; Dong, L. **When Unlearning Fails: Reliable Data Deletion under Post-Training in Agent Networks.** arXiv:2607.28829 (2026).  
    Relevance: especially close adjacent work. It identifies downstream “influence echoes” when target data have already shaped later retained trajectories. This prevents any priority claim for the generic idea that corrupted/deleted data influence later collected trajectories.

14. Nguyen, T. T.; et al. **A Survey of Machine Unlearning.** *ACM Transactions on Intelligent Systems and Technology* (2025). DOI: 10.1145/3749987.  
    Relevance: unlearning scope, streaming removal, retained utility, and exact-versus-approximate removal.

## Runtime/dynamic assurance

15. **Safe autonomous systems in a changing world: Operationalising dynamic safety cases.** *Safety Science* 191, 106965 (2025). DOI: 10.1016/j.ssci.2025.106965.  
    Relevance: monitorability, assessability, and updateability of assurance arguments at runtime.

16. Herd, B.; Kelly, J.; Heinemann, C.; Zacchi, J.-V. **A Subjective Logic-based method for runtime confidence updates in safety arguments.** arXiv:2605.22530 (2026).  
    Relevance: runtime evidence updates confidence in assurance claims; the present work must distinguish scientific validity propagation from generic assurance-case updating.

## Laboratory interoperability substrate

17. OPC Foundation / SPECTARIS. **OPC UA Laboratory and Analytical Device Standard (LADS), Companion Specification 30500.**  
    Relevance: standards-aligned laboratory device state, measurements, alarms/events, methods, and result semantics.

18. `opcua-lads/lads-server-collection`, pH-meter reference simulator (2025–2026).  
    Relevance: Nernst-equation signal model, temperature compensation, slope/offset detuning, raw signal, calibration methods, AFO metadata, and ASM result payloads. The repository explicitly describes the servers as proof-of-concept simulators for demos/integration/reference use.

## Novelty discipline

The study should avoid priority claims until a systematic literature review and external expert review are complete.

The most defensible provisional distinction is scientific-semantic:

- metrological invalidity is not the same relation as computational derivation;
- claim invalidity is not the same relation as experiment-selection influence;
- an experiment selected by a contaminated model may still produce a physically valid artifact or later measurement;
- recovery should preserve these distinctions and be evaluated against strong rollback, retraining, robust-optimization, and blanket-remeasurement baselines.

The July 2026 “influence echo” work in agent networks is the closest conceptual warning found so far. Any paper must cite and distinguish it explicitly.
