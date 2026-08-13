# cgec — Telegram Calls Bug Bounty Research

Research workspace for auditing Telegram’s **VoIP / calls stack** under the official
[Telegram Bug Bounty Program](https://core.telegram.org/bug-bounty).

## Scope

- Primary source: official library [`TelegramMessenger/tgcalls`](https://github.com/TelegramMessenger/tgcalls) (LGPL-3.0), vendored as a git submodule
- Focus: 1:1 calls, group calls, encrypted signaling, reflectors/P2P, media & call-data parsers
- Emphasis: crypto/auth issues **and** memory-safety / overflows in media & framing paths
- Out of scope here: weaponized exploits against third parties, production DoS, non-call product areas

## Layout

```text
third_party/tgcalls/   # upstream submodule (branch: development)
docs/                  # threat model + call pipeline map
notes/review-log.md    # what was reviewed
notes/findings/        # candidate issues for responsible disclosure
```

## Setup

```bash
git clone --recurse-submodules <this-repo-url>
# or after plain clone:
git submodule update --init --recursive
```

Update tgcalls:

```bash
cd third_party/tgcalls && git fetch origin && git checkout origin/development
cd ../.. && git add third_party/tgcalls && git commit -m "Bump tgcalls submodule"
```

## Disclosure

Valid issues should be reported to **security@telegram.org** per Telegram’s bounty rules.
Do not use this workspace to target other users’ accounts or abuse production infrastructure.

## License

- This research scaffolding: see repository license / default rights of the repo owner.
- `third_party/tgcalls`: **GNU LGPL v3** — see `third_party/tgcalls/LICENSE`.
