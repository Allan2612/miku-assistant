import asyncio
from core.llm import MikuBrain

async def test_fallback():
    # Pass an invalid primary model to test auto-fallback to the working secondary model
    brain = MikuBrain(
        model_name="non-existent-fake-model-12345",
        models_fallback=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    )
    print("Testing auto-fallback when primary model fails...")
    emotion, answer, farewell = await brain.chat("Hola Miku, dime qué color te gusta")
    print(f"Fallback SUCCESS!")
    print(f"  Active model: {brain.current_model}")
    print(f"  Emotion: {emotion}")
    print(f"  Answer: {answer}")
    assert brain.current_model in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    print("Test passed successfully!")

if __name__ == "__main__":
    asyncio.run(test_fallback())
