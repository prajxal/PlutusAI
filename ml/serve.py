#!/usr/bin/env python3
"""Serve the trained classifier over HTTP.

    python3 ml/serve.py --model ml/artifacts --port 8100

Then point the application at it:

    PLUTUS_INTENT_MODEL_URL=http://127.0.0.1:8100/classify python3 backend/app.py

The wire contract is the one `backend/services/chat/model_intent.py` expects,
and it is deliberately tiny:

    POST  {"message": "..."}
      ->  {"intent": "price_change", "confidence": 0.97, "metric": null}

The same contract is what a Hugging Face Inference Endpoint or Space has to
honour, so swapping this process for a hosted one changes a URL and nothing
else. Note what the request does *not* carry: no business_id, no products, no
figures. This process cannot leak a customer's numbers because it is never
given any.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def build_app(model_path: str):
    from fastapi import FastAPI
    from pydantic import BaseModel, Field

    from infer import LocalIntentModel

    classifier = LocalIntentModel(model_path)
    app = FastAPI(title="PlutusAI intent model", version="1.0.0")

    class Request(BaseModel):
        message: str = Field(min_length=1, max_length=2000)

    @app.get("/health")
    def health():
        return {"ok": True, "base_model": classifier.config["base_model"]}

    @app.post("/classify")
    def classify(request: Request):
        prediction = classifier.classify(request.message)
        return {"intent": prediction.name,
                "confidence": round(prediction.confidence, 4),
                "metric": prediction.metric}

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(HERE, "artifacts"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8100)
    args = ap.parse_args()

    import uvicorn

    print(f"  intent model on http://{args.host}:{args.port}/classify")
    uvicorn.run(build_app(args.model), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
