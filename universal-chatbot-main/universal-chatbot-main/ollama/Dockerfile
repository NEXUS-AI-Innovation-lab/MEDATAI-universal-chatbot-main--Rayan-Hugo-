# Base image with Ollama
FROM ollama/ollama:latest

# Required for Cloud Run: run Ollama without needing privileged mode
ENV OLLAMA_NO_SANDBOX=1

# Start Ollama server in background, pull all models, then stop
RUN ollama serve & \
    sleep 5 && \
    ollama pull embeddinggemma:latest && \
    pkill ollama

# Expose the Ollama server port
EXPOSE 11434

# Start Ollama server
CMD ["serve"]