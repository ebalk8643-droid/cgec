# cgec — Telegram Calls Bug Bounty Research

Research workspace for auditing Telegram’s **VoIP / calls stack** under the official
[Telegram Bug Bounty Program](https://core.telegram.org/bug-bounty).

## How research was done

1. Vendored official [`TelegramMessenger/tgcalls`](https://github.com/TelegramMessenger/tgcalls) (`development`) as a git submodule — not full Android/iOS trees.
2. Mapped the call pipeline (MTProto → E2E keys → encrypted signaling → P2P/reflector → media / group demux) in `docs/call-pipeline-map.md`.
3. Built a threat model (`docs/threat-model.md`) and reviewed P0 surfaces: crypto framing, gzip, message codecs, group media parsers, reflector sizing, join JSON, logging.
4. Wrote candidate findings under `notes/findings/`, triaged in `notes/triage.md`.
5. Polished top issues into submission drafts under `notes/submission/` for `security@telegram.org`.
6. Validated finding 001 offline with `scripts/validate_finding_001_padding.py` (no production traffic, no third-party targeting).

## Scope

- Focus: 1:1 calls, group calls, encrypted signaling, reflectors/P2P, media & call-data parsers
- Emphasis: crypto/auth issues **and** memory-safety / overflows in media & framing paths
- Out of scope here: weaponized exploits against third parties, production DoS campaigns, non-call product areas

## Layout

```text
third_party/tgcalls/     # upstream submodule (branch: development)
docs/                    # threat model, pipeline map, harness notes
notes/review-log.md      # review checklist
notes/triage.md          # submit vs defer decisions
notes/findings/          # raw candidate notes
notes/submission/        # bounty-ready drafts (top issues)
scripts/                 # inventory + offline validators
```

## Setup

```bash
git clone --recurse-submodules <this-repo-url>
# or after plain clone:
git submodule update --init --recursive
```

Offline check for finding 001:

```bash
python3 scripts/validate_finding_001_padding.py
```

## Disclosure

Report valid issues to **security@telegram.org** per Telegram’s bounty rules.
Start from `notes/submission/` drafts. Do not use this workspace to target other users’ accounts or abuse production infrastructure.

## License

- This research scaffolding: see repository license / default rights of the repo owner.
- `third_party/tgcalls`: **GNU LGPL v3** — see `third_party/tgcalls/LICENSE`.
