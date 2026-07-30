from google import genai


if __name__ == "__main__":
    client = genai.Client()
    print("🔍 Querying available embedding models...")
    for model in client.models.list():
        supported_actions = model.supported_actions or []
        if "embed" in model.name.lower() or "embedContent" in supported_actions:
            print(f"✅ Name: {model.name} | Actions: {supported_actions}")
