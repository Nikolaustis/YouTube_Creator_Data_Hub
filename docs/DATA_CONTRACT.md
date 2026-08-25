# Data Contract: Fact / Derived / AI / Human / Effective

V3.10 standardizes cross-domain judgments through `data_assertions`.

- `fact`: imported/API-observed fact.
- `derived`: deterministic rule or calculation.
- `ai`: model inference.
- `human`: explicit user decision/override.
- `effective`: resolved value used by business logic; default priority is `human > ai > derived > fact`.

Each assertion records entity, stable field ID, value JSON, layer, confidence/source, rule version, observation time and creation time. Existing video labels and availability override tables remain authoritative for their legacy workflows; the contract layer mirrors/extends them so future Workbench features do not invent new precedence semantics per page.
