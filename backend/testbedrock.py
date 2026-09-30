import boto3
import json
import sys
import time


REGION = "ap-south-1"
MODEL = "minimax.minimax-m2"


def main():
    print("=" * 70)
    print("AWS BEDROCK MINIMAX ERP TEST")
    print("=" * 70)
    print(f"Region : {REGION}")
    print(f"Model  : {MODEL}")
    print()

    try:
        client = boto3.client(
            "bedrock-runtime",
            region_name=REGION,
        )

        prompt = """
You are an ERP sales data extraction assistant.

Analyze the following sales record.

Customer: ACCURATE RUB TECH
Product: APCOFLEX NVC573E
Quantity: 175
Unit: KGs
Month: April

Return ONLY valid JSON using exactly this structure:

{
  "customer": "ACCURATE RUB TECH",
  "product": "APCOFLEX NVC573E",
  "quantity": 175,
  "unit": "KG",
  "month": "April"
}

Do not provide markdown.
Do not provide explanations.
Return only the JSON object.
"""

        print("Sending request to Bedrock...")
        start = time.perf_counter()

        response = client.converse(
            modelId=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": prompt
                        }
                    ],
                }
            ],
            inferenceConfig={
                "temperature": 0.0,
                "maxTokens": 800,
            },
        )

        latency = round((time.perf_counter() - start) * 1000)

        print(f"HTTP Status : {response.get('ResponseMetadata', {}).get('HTTPStatusCode')}")
        print(f"Latency     : {latency} ms")
        print(f"Stop Reason : {response.get('stopReason')}")
        print(f"Usage       : {response.get('usage')}")
        print()

        content = response.get("output", {}).get("message", {}).get("content", [])

        print(f"Content Blocks: {len(content)}")
        print()

        final_text = ""

        for index, block in enumerate(content):
            print(f"BLOCK {index}")
            print(f"Keys: {list(block.keys())}")

            if "text" in block:
                print("Type: FINAL TEXT")
                print("Text:")
                print(block["text"])
                print()
                final_text += str(block["text"])

            elif "reasoningContent" in block:
                print("Type: REASONING CONTENT")
                print("Reasoning content received.")
                print()

            else:
                print("Type: UNKNOWN")
                print()

        print("=" * 70)
        print("FINAL RESULT")
        print("=" * 70)

        if final_text.strip():
            print("STATUS: SUCCESS")
            print()
            print("Final text returned by MiniMax:")
            print(final_text.strip())

            # Try to validate JSON
            try:
                parsed = json.loads(final_text.strip())

                print()
                print("JSON VALIDATION: SUCCESS")
                print(json.dumps(parsed, indent=2))

            except json.JSONDecodeError as exc:
                print()
                print("JSON VALIDATION: FAILED")
                print(f"Reason: {exc}")

        else:
            print("STATUS: NO FINAL TEXT")
            print()
            print(
                "MiniMax returned no usable 'text' content block."
            )
            print(
                "This is the condition that can produce "
                "'Bedrock returned an empty response' in the application."
            )

        print("=" * 70)

    except Exception as exc:
        print()
        print("=" * 70)
        print("BEDROCK TEST FAILED")
        print("=" * 70)
        print(type(exc).__name__)
        print(str(exc))
        print("=" * 70)

        sys.exit(1)


if __name__ == "__main__":
    main()