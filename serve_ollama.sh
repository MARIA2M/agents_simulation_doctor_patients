# serve_ollama.sh — source it:  . serve_ollama.sh
#
# Starts an Ollama for this project on its own port, reading the shared model
# store. Its own port because a machine may already run one on 11434 against a
# different store, and OLLAMA_MODELS only takes effect when the server starts.

PORT=${PORT:-11500}

export OLLAMA_MODELS=/gpfs/projects/bsc02/llm_models/ollama
export OLLAMA_HOST=127.0.0.1:$PORT
export PATH=/gpfs/projects/bsc02/llm_models/ollama-bin/bin:$PATH

# Read by load_config, and recorded in metadata.server.ollama_url.
export OLLAMA_URL=http://127.0.0.1:$PORT

if curl -s --max-time 2 "$OLLAMA_URL/api/tags" > /dev/null; then
    echo "[ollama] already answering on $OLLAMA_URL"
else
    ollama serve > "/tmp/ollama-ahead-$USER-$PORT.log" 2>&1 &
    for _ in $(seq 1 30); do
        curl -s --max-time 2 "$OLLAMA_URL/api/tags" > /dev/null && break
        sleep 1
    done
    echo "[ollama] started on $OLLAMA_URL (log: /tmp/ollama-ahead-$USER-$PORT.log)"
fi

curl -s "$OLLAMA_URL/api/tags" | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | sed 's/^/[ollama]   /'
