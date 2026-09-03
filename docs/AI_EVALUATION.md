# AI evaluation

The evaluation harness checks three engineering properties:

1. structured-output contract completion;
2. evidence-key coverage;
3. unsupported evidence references.

Offline CI mode validates the evaluator itself:

```bash
python -m creator_hub.portfolio.ai_eval
```

To evaluate saved model outputs:

```bash
python -m creator_hub.portfolio.ai_eval --outputs evals/results/model_outputs.jsonl
```

The offline fixture intentionally scores 1.0 when the evaluator is functioning. This is **not** a model-quality result and must not be cited as one.
