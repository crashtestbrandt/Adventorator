"""
Test LLMClient with an active Ollama server.
"""

import asyncio
import pytest
from Adventorator.config import Settings
from Adventorator.llm import LLMClient

async def test_llm_generate_response(verbose=False):
    # Configure settings for the LLMClient
    if verbose:
        print("Configuring settings for LLMClient...")
    settings = Settings(
        llm_api_url="http://localhost:8901/api/chat",
        llm_model_name="qwen3:30b-a3b-instruct-2507-q4_K_M",
        llm_default_system_prompt="You are a helpful assistant."
    )

    # Initialize the LLMClient
    if verbose:
        print("Initializing LLMClient...")
    llm_client = LLMClient(settings)

    # Define the test messages
    messages = [
        {"role": "user", "content": "Tell me about Jupiter."}
    ]
    if verbose:
        print(f"Sending messages: {messages}")

    # Call the generate_response method
    response = await llm_client.generate_response(messages)

    # Validate the response
    if verbose:
        print(f"Received response: {response}")
    assert response is not None, "Response should not be None"
    assert isinstance(response, str), "Response should be a string"
    assert len(response) > 0, "Response should not be empty"

    # Close the client
    if verbose:
        print("Closing LLMClient...")
    await llm_client.close()

if __name__ == "__main__":
    import asyncio
    print("Running test_llm_generate_response directly...")
    asyncio.run(test_llm_generate_response(verbose=True))