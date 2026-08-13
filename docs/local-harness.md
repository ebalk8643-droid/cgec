# Local harness notes

## Offline validators

```bash
python3 scripts/validate_finding_001_padding.py
```

Reproduces the offset-past-end condition for finding 001 without network access.

## Upstream tgcalls CLI (optional)

Upstream `third_party/tgcalls` includes Docker/Bazel CLI for P2P/reflector smoke tests.
Building the full WebRTC stack is heavy; not required for the static findings already documented.

If built later, prefer:

```bash
# from upstream docs — P2P loopback only
docker build -t tgcalls-test third_party/tgcalls
docker run --rm tgcalls-test --mode p2p --duration 5 --quiet
```

Do **not** run mass reflector load tests against production.
