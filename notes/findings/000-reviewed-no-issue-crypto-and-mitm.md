# 000 — Reviewed, no issue filed (crypto core + MitM verification in-library)

## EncryptedConnection / CryptoHelper
Reviewed for MAC bypass, counter replay, and unbounded decrypt. Incoming path checks size, derives AES-CTR key/IV from msgKey, verifies SHA256 msgKey slice in const-time, and rejects duplicate/old counters. No bounty candidate filed from this pass.

## Key verification / emoji / group commit-reveal
`tgcalls` does not implement call-key agreement UI or emoji comparison. It accepts `EncryptionKey` from the host app. MitM resistance therefore depends on Desktop/Android/iOS + MTProto E2E docs, not this submodule. Explicitly marked reviewed-with-no-in-tree-finding for Phase 3 acceptance.
