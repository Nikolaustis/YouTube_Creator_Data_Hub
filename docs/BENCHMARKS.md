# Benchmarks

Run fixed synthetic profiles:

```bash
python -m creator_hub.portfolio.benchmark --profile small
python -m creator_hub.portfolio.benchmark --profile medium --json benchmarks/results/medium.json
python -m creator_hub.portfolio.benchmark --profile large --json benchmarks/results/large.json
```

Profiles are deterministic and record Python version, operating system, machine, processor and CPU count. Measurements include dataset generation, cold/warm Dashboard build, Creator listing, Creator Facts payload, Metric Base payload and Workspace semantic indexing.

Do not compare numbers across machines without reporting the environment. Do not commit fabricated benchmark values.
