"""Smoke test for Claude mode: verifies the ANTHROPIC_API_KEY works and the
agent's Claude "Brain" path responds. Run: uv run python test_claude_mode.py"""

import asyncio
import config
from vision_helper import VisionAssistant


async def main() -> None:
    if not config.ANTHROPIC_API_KEY:
        print("[FAIL] No ANTHROPIC_API_KEY found. Add it to agent/.env and retry.")
        return

    print(f"Brain (strategy) model: {config.STRATEGY_MODEL}")
    print(f"Eyes  (vision)   model: {config.VISION_MODEL}")
    va = VisionAssistant()
    print(f"OpenAI client active?   {va.openai_client is not None}  (Claude mode = False)")

    print("\nCalling Claude to generate a navigation plan...")
    steps = await va.generate_navigation_plan(
        "Find the latest release version, date, and author", "openclaw/openclaw"
    )
    if steps:
        print("[OK] Claude responded. Plan:")
        for i, step in enumerate(steps, 1):
            print(f"   {i}. {step}")
    else:
        print("[WARN] Claude returned no steps (check the error printed above).")


if __name__ == "__main__":
    asyncio.run(main())
