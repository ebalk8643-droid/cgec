#!/usr/bin/env bash
# List high-interest tgcalls paths for review.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="$ROOT/third_party/tgcalls/tgcalls"
for p in \
  EncryptedConnection.cpp CryptoHelper.cpp Message.cpp \
  utils/gzip.cpp \
  v2/SignalingEncryption.cpp v2/Signaling.cpp \
  v2/ReflectorPort.cpp v2/ContentNegotiation.cpp \
  group/AudioStreamingPartInternal.cpp group/VideoStreamingPart.cpp \
  group/GroupJoinPayloadInternal.cpp group/GroupNetworkManager.cpp
do
  f="$BASE/$p"
  if [[ -f "$f" ]]; then
    wc -l "$f"
  else
    echo "MISSING $p"
  fi
done
