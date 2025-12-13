#!/bin/bash

# Check Ollama configuration and models

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Checking Ollama configuration...${NC}\n"

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e "${RED}✗ Ollama is not running!${NC}"
    echo -e "${YELLOW}Start it with: ollama serve${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Ollama is running${NC}"

# Get available models
echo -e "\n${YELLOW}Available models:${NC}"
MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "
import sys, json
data = json.load(sys.stdin)
for model in data.get('models', []):
    print(model['name'])
")

if [ -z "$MODELS" ]; then
    echo -e "${RED}✗ No models found!${NC}"
    echo -e "${YELLOW}Pull a model with: ollama pull qwen2.5:7b${NC}"
    exit 1
fi

echo "$MODELS" | while read -r model; do
    echo -e "  ${GREEN}✓${NC} $model"
done

# Check for Qwen models
QWEN_MODEL=$(echo "$MODELS" | grep -i "qwen" | head -1)

if [ -z "$QWEN_MODEL" ]; then
    echo -e "\n${YELLOW}No Qwen model found. Pull one with:${NC}"
    echo -e "  ollama pull qwen2.5:7b"
    exit 1
fi

echo -e "\n${GREEN}✓ Found Qwen model: ${QWEN_MODEL}${NC}"

# Check current config
echo -e "\n${YELLOW}Current config.py settings:${NC}"
CURRENT_MODEL=$(grep "ollama_model_main" src/config.py | cut -d'"' -f2)
echo -e "  ollama_model_main: ${CURRENT_MODEL}"

# Compare
if [ "$CURRENT_MODEL" != "$QWEN_MODEL" ]; then
    echo -e "\n${YELLOW}⚠ Model mismatch!${NC}"
    echo -e "  Config uses: ${RED}${CURRENT_MODEL}${NC}"
    echo -e "  Available:   ${GREEN}${QWEN_MODEL}${NC}"
    echo -e "\n${YELLOW}Update config.py to use: ${QWEN_MODEL}${NC}"
    echo -e "Or set in .env file:"
    echo -e "  OLLAMA_MODEL_MAIN=${QWEN_MODEL}"
else
    echo -e "\n${GREEN}✓ Model configuration is correct!${NC}"
fi

# Test the model
echo -e "\n${YELLOW}Testing model with a simple query...${NC}"
RESPONSE=$(curl -s -X POST http://localhost:11434/api/generate \
    -d "{\"model\":\"${QWEN_MODEL}\",\"prompt\":\"Say hello in one word\",\"stream\":false}" \
    2>&1)

if echo "$RESPONSE" | grep -q '"response"'; then
    ANSWER=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('response', ''))")
    echo -e "${GREEN}✓ Model works! Response: ${ANSWER}${NC}"
else
    echo -e "${RED}✗ Model test failed!${NC}"
    echo "$RESPONSE"
    exit 1
fi

echo -e "\n${GREEN}✓ Ollama is properly configured and ready to use!${NC}"
