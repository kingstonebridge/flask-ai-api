#!/usr/bin/env bash
set -e

echo "Downloading pre-trained crypto trading models..."
mkdir -p models
cd models

wget https://github.com/notadamking/Stock-Trading-Visualization/releases/download/v1.0/ppo_crypto.zip
wget https://huggingface.co/microsoft/DialoGPT-medium/resolve/main/pytorch_model.bin

echo "✅ Models downloaded successfully"
