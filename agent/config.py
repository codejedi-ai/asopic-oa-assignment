"""
Configuration settings
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Model Configuration — Claude-driven ("Brain" = strategy, "Eyes" = vision).
# Both roles run on Claude so the agent works with only an ANTHROPIC_API_KEY.
# To reduce cost, set EYES (TAGGING/VISION) to a cheaper model e.g. claude-haiku-4-5.
STRATEGY_MODEL = os.getenv("STRATEGY_MODEL", "claude-haiku-4-5")  # Brain
VISION_MODEL = os.getenv("VISION_MODEL", "claude-haiku-4-5")      # Eyes
TAGGING_MODEL = os.getenv("TAGGING_MODEL", "claude-haiku-4-5")    # Eyes

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Navigation Settings
MAX_NAVIGATION_STEPS = 15
WAIT_TIMEOUT = 10000  # ms
STEP_DELAY = 5000  # ms
# File Paths — all agent data lives under ~/.clio
# (Windows: C:\Users\<user>\.clio, Linux/macOS: ~/.clio). Override with CLIO_HOME.
CLIO_HOME = Path(os.getenv("CLIO_HOME", str(Path.home() / ".clio")))
DATA_DIR = str(CLIO_HOME / "data")
SCREENSHOT_DIR = str(CLIO_HOME / "screenshots")
CONFIG_DIR = str(CLIO_HOME / "config")
BROWSER_DATA_DIR = str(CLIO_HOME / "browser_data")
DEBUG_DIR = str(CLIO_HOME / "debug_artifacts")
for _d in (DATA_DIR, SCREENSHOT_DIR, CONFIG_DIR, BROWSER_DATA_DIR, DEBUG_DIR):
    Path(_d).mkdir(parents=True, exist_ok=True)

# GitHub URLs
GITHUB_HOMEPAGE = "https://github.com"