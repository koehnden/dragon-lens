"""Run example with option to reuse existing prompt results."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_existing_vertical(vertical_name: str) -> Optional[int]:
    """Check if vertical exists and return its ID."""
    try:
        response = requests.get(
            f"http://localhost:{settings.api_port}/api/v1/verticals",
            params={"name": vertical_name}
        )
        if response.status_code == 200:
            verticals = response.json()
            if verticals:
                return verticals[0]["id"]
    except requests.RequestException:
        pass
    return None


def check_existing_answers(vertical_id: int) -> bool:
    """Check if there are existing LLM answers for a vertical."""
    try:
        response = requests.get(
            f"http://localhost:{settings.api_port}/api/v1/tracking/runs",
            params={"vertical_id": vertical_id}
        )
        if response.status_code == 200:
            runs = response.json()
            for run in runs:
                if run.get("status") == "completed":
                    return True
    except requests.RequestException:
        pass
    return False


def delete_existing_vertical(vertical_name: str) -> bool:
    """Delete existing vertical and all associated data."""
    try:
        vertical_id = check_existing_vertical(vertical_name)
        if not vertical_id:
            return True
        
        logger.info(f"Deleting existing vertical '{vertical_name}' (ID: {vertical_id})...")
        
        delete_jobs_response = requests.delete(
            f"http://localhost:{settings.api_port}/api/v1/tracking/jobs",
            params={"vertical_name": vertical_name}
        )
        
        if delete_jobs_response.status_code == 200:
            deleted_count = delete_jobs_response.json().get("deleted_count", 0)
            logger.info(f"Deleted {deleted_count} existing job(s)")
        
        delete_vertical_response = requests.delete(
            f"http://localhost:{settings.api_port}/api/v1/verticals/{vertical_id}"
        )
        
        if delete_vertical_response.status_code == 200:
            logger.info(f"Deleted vertical {vertical_id}")
            return True
        else:
            logger.warning(f"Could not delete vertical {vertical_id}")
            return False
            
    except requests.RequestException as e:
        logger.error(f"Error deleting vertical: {e}")
        return False


def configure_api_key(provider: str, api_key: str) -> bool:
    """Configure API key for the provider."""
    try:
        payload = {
            "provider": provider,
            "api_key": api_key,
            "name": f"{provider} API Key"
        }
        
        response = requests.post(
            f"http://localhost:{settings.api_port}/api/v1/api-keys",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code in (200, 201):
            print(f"✓ API key configured for {provider}")
            return True
        else:
            print(f"⚠  Failed to configure API key: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"⚠  Error configuring API key: {e}")
        return False


def create_tracking_job(example_file: Path, provider: str, model_name: str) -> bool:
    """Create a new tracking job."""
    try:
        with open(example_file, "r") as f:
            example_data = json.load(f)
        
        example_data["provider"] = provider
        example_data["model_name"] = model_name
        
        response = requests.post(
            f"http://localhost:{settings.api_port}/api/v1/tracking/jobs",
            json=example_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 201:
            result = response.json()
            logger.info(f"Created tracking job: {result}")
            return True
        else:
            logger.error(f"Failed to create tracking job: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error creating tracking job: {e}")
        return False


def check_api_key_configured(provider: str) -> bool:
    if provider == "qwen":
        return True

    env_keys = {
        "deepseek": settings.deepseek_api_key,
        "kimi": settings.kimi_api_key,
    }
    if env_keys.get(provider):
        return True

    try:
        response = requests.get(
            f"http://localhost:{settings.api_port}/api/v1/api-keys",
            params={"provider": provider}
        )
        if response.status_code == 200:
            api_keys = response.json()
            return len(api_keys) > 0
    except requests.RequestException:
        pass
    return False


def parse_provider_and_model(provider_arg: str) -> tuple[str, str]:
    mapping = {
        "qwen": ("qwen", "qwen2.5:7b-instruct-q4_0"),
        "deepseek-chat": ("deepseek", "deepseek-chat"),
        "deepseek-reasoner": ("deepseek", "deepseek-reasoner"),
        "kimi-8k": ("kimi", "moonshot-v1-8k"),
        "kimi-32k": ("kimi", "moonshot-v1-32k"),
        "kimi-128k": ("kimi", "moonshot-v1-128k"),
    }
    return mapping.get(provider_arg, (provider_arg, provider_arg))


def prompt_for_api_key_if_needed(provider: str, api_key_arg: Optional[str]) -> Optional[str]:
    if provider == "qwen":
        return None

    if api_key_arg:
        return api_key_arg

    env_keys = {
        "deepseek": settings.deepseek_api_key,
        "kimi": settings.kimi_api_key,
    }
    if env_keys.get(provider):
        print(f"✓ API key for {provider} found in .env")
        return None

    if check_api_key_configured(provider):
        print(f"✓ API key for {provider} configured in database")
        return None
    
    env_var_name = f"{provider.upper()}_API_KEY"
    print(f"⚠  No API key configured for {provider}")
    print(f"   Remote models require an API key to run.")
    print(f"   You can:")
    print(f"   1. Configure it via the UI: http://localhost:{settings.streamlit_port}")
    print(f"   2. Pass it with --api-key YOUR_KEY")
    print(f"   3. Add it to your .env file: {env_var_name}=your_key")
    print()
    
    try:
        api_key = input(f"Enter API key for {provider} (or press Enter to skip): ").strip()
        if api_key:
            return api_key
        else:
            print(f"⚠  No API key provided. {provider} jobs may fail.")
            return None
    except EOFError:
        print(f"⚠  Cannot prompt for API key in non-interactive mode.")
        print(f"   Please configure API key via UI or --api-key flag.")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run example with option to reuse existing prompt results")
    parser.add_argument(
        "--reuse-prompt-results",
        action="store_true",
        default=True,
        help="Reuse existing prompt results if available. Default: True"
    )
    parser.add_argument(
        "--no-reuse-prompt-results",
        action="store_false",
        dest="reuse_prompt_results",
        help="Do not reuse existing prompt results (run from scratch)"
    )
    parser.add_argument(
        "--provider",
        default="qwen",
        choices=["qwen", "deepseek-chat", "deepseek-reasoner", "kimi-8k", "kimi-32k", "kimi-128k"],
        help="LLM provider to use. Default: qwen"
    )
    parser.add_argument(
        "--model-name",
        default=None,
        help="Model name to use. Default: based on provider"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key for DeepSeek models (if not already configured)"
    )
    
    args = parser.parse_args()
    
    example_file = Path(__file__).parent.parent / "examples" / "suv_example.json"
    if not example_file.exists():
        logger.error(f"Example file not found: {example_file}")
        sys.exit(1)
    
    with open(example_file, "r") as f:
        example_data = json.load(f)

    vertical_name = example_data.get("vertical_name", "SUV Cars")

    provider, model_name = parse_provider_and_model(args.provider)
    if args.model_name:
        model_name = args.model_name

    print("=" * 60)
    print("DragonLens Example Runner")
    print("=" * 60)
    print(f"Vertical: {vertical_name}")
    print(f"Provider: {provider}")
    print(f"Model: {model_name}")
    print(f"Reuse prompt results: {args.reuse_prompt_results}")
    print()

    api_key = prompt_for_api_key_if_needed(provider, args.api_key)

    if api_key:
        if not configure_api_key(provider, api_key):
            print("⚠  Continuing without API key configuration...")
    
    vertical_id = check_existing_vertical(vertical_name)
    
    if vertical_id:
        has_existing_answers = check_existing_answers(vertical_id)
        
        if has_existing_answers and args.reuse_prompt_results:
            print(f"✓ Found existing vertical '{vertical_name}' with prompt results")
            print("  Prompt results will be reused for extraction")
            print("  No new LLM calls will be made")
            print()
            print("To run from scratch, use: --no-reuse-prompt-results")
            print()
            return
        
        elif not args.reuse_prompt_results:
            print(f"Found existing vertical '{vertical_name}'")
            print("Deleting it to start fresh...")
            if not delete_existing_vertical(vertical_name):
                print("⚠ Could not delete existing vertical, attempting to create new job anyway...")
    
    print("Creating new tracking job...")
    if create_tracking_job(example_file, provider, model_name):
        print("✅ Tracking job created successfully!")
        print()
        print("Next steps:")
        print(f"  View runs:    curl http://localhost:{settings.api_port}/api/v1/tracking/runs | jq")
        print(f"  Check status: curl http://localhost:{settings.api_port}/api/v1/tracking/runs/1 | jq")
        print(f"  View in UI:   http://localhost:{settings.streamlit_port}")
    else:
        print("❌ Failed to create tracking job")
        sys.exit(1)


if __name__ == "__main__":
    main()
