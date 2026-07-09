## Summary

## Validation

- [ ] `python -m compileall -q autopilot_nodekit tests`
- [ ] `python -m pytest -q`

## Safety / control-plane checklist

- [ ] Does not bypass verifier-authoritative DONE.
- [ ] Does not bypass Santa review where required.
- [ ] Does not silently disable repair/final audit.
- [ ] Handles Windows/Linux assumptions explicitly.
- [ ] Does not include private logs, data, paths, secrets, or model weights.
