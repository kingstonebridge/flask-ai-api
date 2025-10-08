from flask import Flask, request, jsonify
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
import torch

app = Flask(__name__)

# ----------- MODEL SETUP ------------
# Replace with your own model or any public one on Hugging Face
MODEL_NAME = "facebook/bart-large-cnn"

# Load model + tokenizer
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

# Create a summarization pipeline
summarizer = pipeline("summarization", model=model, tokenizer=tokenizer, device=0 if torch.cuda.is_available() else -1)

# ----------- ROUTES ------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "message": "Model API is running"}), 200


@app.route("/predict", methods=["POST"])
def predict():
    """POST JSON: { "text": "your long article or sentence here" }"""
    try:
        data = request.get_json()
        text = data.get("text", "").strip()

        if not text:
            return jsonify({"error": "Missing 'text' field"}), 400

        # Run model inference
        summary = summarizer(text, max_length=150, min_length=30, do_sample=False)

        return jsonify({
            "input": text,
            "summary": summary[0]['summary_text']
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Run the app as a web service
    app.run(host="0.0.0.0", port=8080)
