import os
import time
import boto3

def test_api():
    model_id = os.environ.get("BEDROCK_MODEL_ID", "google.gemma-3-27b-it")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    print(f"Testing AWS Bedrock connection ({model_id}) in {region}...")
    client = boto3.client("bedrock-runtime", region_name=region)

    start_time = time.time()
    try:
        response = client.converse(
            modelId=model_id,
            system=[{"text": "You are a test assistant. Answer in 1 short sentence."}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "Confirm that the API connection is active."}]
                }
            ],
            inferenceConfig={
                "maxTokens": 100,
                "temperature": 0.1
            }
        )
        elapsed = time.time() - start_time
        reply = response["output"]["message"]["content"][0]["text"]
        input_tokens = response["usage"]["inputTokens"]
        output_tokens = response["usage"]["outputTokens"]

        print("\n=== SUCCESS ===")
        print(f"Latency: {elapsed:.2f}s")
        print(f"Tokens Used: {input_tokens} input, {output_tokens} output")
        print(f"Est. Cost: < $0.0001")
        print(f"Response: {reply}\n")

    except Exception as e:
        print("\n=== ERROR ===")
        print(f"API Call Failed: {e}\n")

if __name__ == "__main__":
    test_api()