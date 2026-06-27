# GitHub Release Navigator (Service 2)

A robust, vision-based autonomous agent designed to navigate GitHub and extract semantic release information without relying on fragile CSS selectors.

## 🚀 Overview

The **GitHub Release Navigator** solves the "brittle scraper" problem. Instead of looking for specific classes or IDs (which often change), this agent uses **Computer Vision (GPT-4o)** to "see" the page and **Reinforcement Learning (RL) heuristics** to "decide" where to click. It runs on a local **Model Context Protocol (MCP)** server that controls a Playwright browser instance.

### Key Capabilities
- **Resilient Navigation**: Finds "Releases" buttons even if the DOM layout changes, by recognizing visual cues (buttons, links, layout).
- **Intelligent Planning**: Uses an A* search algorithm (Lesser/Greater A*) to score potential actions based on a weighted prediction model specific to the navigation goal.
- **Vision-Augmented Extraction**: Extracts specific data (Version, Commit Hash, Author) by visually analyzing the release card and correlating it with the HTML structure.
- **Natural Language Control**: Can act on prompts like "Find the latest release for pytorch/pytorch".

## 🛠️ Architecture

The system is composed of three main layers:

1.  **Limbs (MCP Server)**: `mcp_server.py`
    *   Starts a Playwright browser.
    *   Exposes tools: `navigate_to_url`, `click_element`, `get_screenshot`, `get_dom_tree`.
    *   Handles low-level safety checks (e.g., verifying an element is actually clickable).

2.  **Brain (Navigator & Knowledge)**: `navigate.py` & `knowledge.py`
    *   Manages the "Mission" lifecycle.
    *   **Lesser A***: Scans the DOM to find interactive candidates.
    *   **Greater A***: Scores candidates based on Heuristics + Q-Learning + Vision Model confidence.
    *   **Cost Management**: Tracks the "cost" of actions (simulating token/compute budgets).

3.  **Eyes (Vision Helper)**: `vision_helper.py`
    *   Interfaces with OpenAI (GPT-4o) and Anthropic (Claude 3.5 Sonnet).
    *   **Observer**: Describes the current page state to the Brain ("I see a list of releases, the top one is v1.2.3").
    *   **Judge**: Decides if the goal has been reached.

## 📦 Installation

### Prerequisites
- Python 3.10+
- OpenAI API Key (Required for Vision)
- Anthropic API Key (Optional, for strategic reasoning)

### Steps

1.  **Clone the repository** (if not already done).

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Install Playwright Browsers**:
    ```bash
    playwright install chromium
    ```

4.  **Environment Setup**:
    Create a `.env` file in the `service-2` directory:
    ```ini
    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...  
    VISION_MODEL=gpt-4o
    ```

## 🏃 Usage

### Basic CLI
Run the navigator for a specific repository:

```bash
python navigate.py --repo owner/repo
```

**Example:**
```bash
python navigate.py --repo openclaw/openclaw
```

### Advanced Usage

**Using a Custom Start URL & Prompt:**
```bash
python navigate.py --url "https://github.com/explore" --prompt "Find the trending python repo and get its latest release"
```

**Visual vs Headless:**
Currently defaults to **Headed** mode (you will see the browser open) for debugging purposes. To change this, modify `mcp_server.py` line 135: `headless=True`.

## 📂 Project Structure

| File | Description |
|------|-------------|
| `navigate.py` | **Main Entry Point**. Runs the autonomous agent loop. |
| `mcp_server.py` | **Tool Layer**. The MCP server interacting with Playwright. |
| `vision_helper.py`| **AI Layer**. Handlers for GPT-4o/Claude vision & logic. |
| `knowledge.py` | **Memory**. Q-learning table implementation. |
| `page_tracker.py` | Utils for tracking page state and history. |
| `config.py` | Configuration constants and environment loading. |
| `debug_artifacts/`| Stores screenshots and DOM dumps during runs. |
| `data/` | Output directory for results (`output.json`) and cost logs. |

## 🧪 Testing

Run the test suite to verify components:

```bash
pytest tests/
```

## 🤝 Contribution

1.  Fork the Project
2.  Create your Feature Branch
3.  Commit your Changes
4.  Push to the Branch
5.  Open a Pull Request

---
*Built with ❤️ by the Advanced Agentic Coding Team*