#!/usr/bin/env bash
# Installs Ollama (if missing), starts its server, and pulls the model
# used by src/intelligence/agent/ollama_client.py.
#
# Safe to re-run: every step checks current state first and skips
# anything already done, so re-running just verifies everything is
# still up and running.
#
# Usage:
#   ./scripts/setup_local_llm.sh
#   OLLAMA_MODEL=qwen2.5:3b ./scripts/setup_local_llm.sh   # override model

set -euo pipefail

MODEL="${OLLAMA_MODEL:-qwen2.5:1.5b}"
HOST="${OLLAMA_HOST_URL:-http://localhost:11434}"

log() { printf '[setup_local_llm] %s\n' "$1"; }

# --- 1. Install Ollama if not already present ---
if command -v ollama >/dev/null 2>&1; then
    log "Ollama already installed ($(ollama --version 2>&1 | head -n1))."
else
    case "$(uname -s)" in
        Linux|Darwin)
            log "Installing Ollama via official install script..."
            curl -fsSL https://ollama.com/install.sh | sh
            ;;
        *)
            log "Unsupported OS for auto-install. Install Ollama manually from https://ollama.com/download and re-run this script."
            exit 1
            ;;
    esac
fi

# --- 2. Start the Ollama server if it isn't already responding ---
if curl -fsS "${HOST}/api/version" >/dev/null 2>&1; then
    log "Ollama server already running at ${HOST}."
else
    log "Starting Ollama server in the background..."
    nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
    disown

    for _ in $(seq 1 30); do
        if curl -fsS "${HOST}/api/version" >/dev/null 2>&1; then
            log "Ollama server is up."
            break
        fi
        sleep 1
    done

    if ! curl -fsS "${HOST}/api/version" >/dev/null 2>&1; then
        log "Server did not come up after 30s — check /tmp/ollama-serve.log"
        exit 1
    fi
fi

# --- 3. Pull the model if not already present ---
if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "${MODEL}"; then
    log "Model ${MODEL} already pulled."
else
    log "Pulling ${MODEL} (first run only, ~1GB download)..."
    ollama pull "${MODEL}"
fi

# --- 4. Smoke test ---
log "Running a smoke-test prompt against ${MODEL}..."
curl -fsS "${HOST}/api/generate" -d "{\"model\": \"${MODEL}\", \"prompt\": \"Reply with exactly: OK\", \"stream\": false}" \
    | python3 -c "import json,sys; print('Model response:', json.load(sys.stdin)['response'].strip())"

log "Ready. The trading agent's OllamaClient (src/intelligence/agent/ollama_client.py) will talk to ${HOST} using model '${MODEL}'."
