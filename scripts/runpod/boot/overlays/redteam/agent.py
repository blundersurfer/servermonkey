#!/usr/bin/env python3
"""
Red Team ReAct Agent — Interactive offensive security assistant.

Single-file agent using OpenAI SDK pointed at local vLLM instances.
Supports dual-model operation: planner (strategic) and executor (tactical).

Usage:
    python agent.py                    # Default: plan mode
    python agent.py --mode exec        # Tactical execution mode
    python agent.py --mode plan        # Strategic planning mode
    python agent.py --prompt recon     # Load prompt template
    python agent.py --list-prompts     # Show available prompts

In-session commands:
    /prompts          List available prompt templates
    /load <name>      Load a prompt template
    /clear            Clear conversation history
    /save <file>      Save conversation to file
    /mode             Show current mode
    /mode plan|exec   Switch mode (clears history)
    /help             Show commands
    /quit             Exit
"""

import argparse
import json
import readline
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)

try:
    from duckduckgo_search import DDGS
except ImportError:
    print("ERROR: duckduckgo-search not installed. Run: pip install duckduckgo-search")
    sys.exit(1)

# --- Configuration ---

AGENT_DIR = Path(__file__).parent
PROMPTS_DIR = AGENT_DIR / "prompts"

MODES = {
    "plan": {
        "port": 8001,
        "fallback_port": 8000,
        "system_prompt_file": "system-prompt-planner.md",
        "label": "planner (strategic)",
    },
    "exec": {
        "port": 8000,
        "fallback_port": None,
        "system_prompt_file": "system-prompt-executor.md",
        "label": "executor (tactical)",
    },
}

MAX_TOOL_ROUNDS = 5

# --- Tool definitions (OpenAI function calling format) ---

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Use for CVEs, PoCs, techniques, tools, and defensive landscape research.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and read the text content of a web page. Use to read full articles, PoC code, documentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch",
                    },
                },
                "required": ["url"],
            },
        },
    },
]


# --- Tool implementations ---


def tool_web_search(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo and return formatted results."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No results found."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r.get('title', 'No title')}")
            lines.append(f"    URL: {r.get('href', 'N/A')}")
            lines.append(f"    {r.get('body', 'No snippet')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"


def tool_web_fetch(url: str) -> str:
    """Fetch a web page and return stripped text content."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (research agent)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        # Strip HTML tags
        text = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        # Truncate to avoid filling context window
        if len(text) > 8000:
            text = text[:8000] + "\n\n[...truncated at 8000 chars]"
        return text if text else "Page returned empty content."
    except Exception as e:
        return f"Fetch error: {e}"


TOOL_DISPATCH = {
    "web_search": tool_web_search,
    "web_fetch": tool_web_fetch,
}


# --- Model detection ---


def detect_model(port: int) -> str | None:
    """Query vLLM /v1/models endpoint to get the served model name."""
    try:
        url = f"http://127.0.0.1:{port}/v1/models"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        models = data.get("data", [])
        if models:
            return models[0]["id"]
    except Exception:
        pass
    return None


def check_port(port: int) -> bool:
    """Check if a vLLM instance is responding on the given port."""
    return detect_model(port) is not None


# --- System prompt loading ---


def load_system_prompt(mode: str) -> str:
    """Load the system prompt for the given mode."""
    filename = MODES[mode]["system_prompt_file"]
    path = AGENT_DIR / filename
    if path.exists():
        return path.read_text().strip()
    return f"You are a helpful {MODES[mode]['label']} assistant."


def list_prompts() -> list[str]:
    """List available prompt template names."""
    if not PROMPTS_DIR.exists():
        return []
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))


def load_prompt(name: str) -> str | None:
    """Load a prompt template by name."""
    path = PROMPTS_DIR / f"{name}.md"
    if path.exists():
        return path.read_text().strip()
    return None


# --- Agent class ---


class RedTeamAgent:
    def __init__(self, mode: str = "plan", initial_prompt: str | None = None):
        self.mode = mode
        self.port = self._resolve_port(mode)
        self.model = detect_model(self.port)
        if not self.model:
            print(f"ERROR: No model responding on port {self.port}")
            sys.exit(1)

        self.client = OpenAI(
            base_url=f"http://127.0.0.1:{self.port}/v1",
            api_key="not-needed",
        )
        self.system_prompt = load_system_prompt(mode)
        self.messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        self.initial_prompt = initial_prompt

        print(f"\n  Mode:  {MODES[mode]['label']}")
        print(f"  Model: {self.model}")
        print(f"  Port:  {self.port}")
        print(f"  Tools: web_search, web_fetch")
        print(f"  Type /help for commands\n")

    def _resolve_port(self, mode: str) -> int:
        """Resolve the port for a mode, with fallback."""
        cfg = MODES[mode]
        if check_port(cfg["port"]):
            return cfg["port"]
        if cfg["fallback_port"] and check_port(cfg["fallback_port"]):
            print(f"  Note: {mode} model not available on :{cfg['port']}, "
                  f"falling back to :{cfg['fallback_port']}")
            return cfg["fallback_port"]
        # Return primary port — will fail at model detection
        return cfg["port"]

    def switch_mode(self, new_mode: str):
        """Switch to a different mode, clearing history."""
        if new_mode not in MODES:
            print(f"  Unknown mode: {new_mode}. Available: plan, exec")
            return
        if new_mode == self.mode:
            print(f"  Already in {new_mode} mode.")
            return

        self.mode = new_mode
        self.port = self._resolve_port(new_mode)
        self.model = detect_model(self.port)
        if not self.model:
            print(f"  ERROR: No model on port {self.port}")
            return

        self.client = OpenAI(
            base_url=f"http://127.0.0.1:{self.port}/v1",
            api_key="not-needed",
        )
        self.system_prompt = load_system_prompt(new_mode)
        self.messages = [{"role": "system", "content": self.system_prompt}]

        print(f"  Switched to {MODES[new_mode]['label']} (:{self.port}, {self.model})")
        print(f"  History cleared.")

    def chat(self, user_input: str) -> str:
        """Send a message and run the ReAct loop with tool calls."""
        self.messages.append({"role": "user", "content": user_input})

        for round_num in range(MAX_TOOL_ROUNDS):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
            except Exception as e:
                # Fallback: try without tools if model doesn't support them
                if round_num == 0 and "tool" in str(e).lower():
                    try:
                        response = self.client.chat.completions.create(
                            model=self.model,
                            messages=self.messages,
                        )
                    except Exception as e2:
                        return f"Error: {e2}"
                else:
                    return f"Error: {e}"

            choice = response.choices[0]
            msg = choice.message

            # No tool calls — final response
            if not msg.tool_calls:
                self.messages.append({"role": "assistant", "content": msg.content or ""})
                return msg.content or ""

            # Process tool calls
            self.messages.append(msg.model_dump())

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                print(f"  [{fn_name}] {fn_args.get('query', fn_args.get('url', ''))}")

                if fn_name in TOOL_DISPATCH:
                    result = TOOL_DISPATCH[fn_name](**fn_args)
                else:
                    result = f"Unknown tool: {fn_name}"

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        return "(Reached tool call limit. Generating final response...)"

    def handle_command(self, cmd: str) -> bool:
        """Handle slash commands. Returns True if command was handled."""
        parts = cmd.strip().split(None, 1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if command == "/help":
            print("  Commands:")
            print("    /prompts          List prompt templates")
            print("    /load <name>      Load a prompt template")
            print("    /clear            Clear conversation history")
            print("    /save <file>      Save conversation to file")
            print("    /mode             Show current mode")
            print("    /mode plan|exec   Switch mode")
            print("    /help             Show this help")
            print("    /quit             Exit")
            return True

        elif command == "/prompts":
            templates = list_prompts()
            if templates:
                print("  Available prompts:")
                for t in templates:
                    print(f"    - {t}")
            else:
                print("  No prompt templates found.")
            return True

        elif command == "/load":
            if not arg:
                print("  Usage: /load <prompt-name>")
                return True
            content = load_prompt(arg)
            if content:
                self.messages.append({"role": "user", "content": content})
                print(f"  Loaded prompt: {arg}")
                print(f"  Context added. Type your question to continue.")
            else:
                print(f"  Prompt not found: {arg}")
                print(f"  Available: {', '.join(list_prompts())}")
            return True

        elif command == "/clear":
            self.messages = [{"role": "system", "content": self.system_prompt}]
            print("  Conversation cleared.")
            return True

        elif command == "/save":
            if not arg:
                print("  Usage: /save <filename>")
                return True
            try:
                with open(arg, "w") as f:
                    for m in self.messages:
                        if m["role"] == "system":
                            continue
                        role = m.get("role", "?")
                        content = m.get("content", "")
                        if content:
                            f.write(f"## {role.upper()}\n\n{content}\n\n---\n\n")
                print(f"  Saved to {arg}")
            except Exception as e:
                print(f"  Save error: {e}")
            return True

        elif command == "/mode":
            if not arg:
                print(f"  Current mode: {self.mode} ({MODES[self.mode]['label']})")
                print(f"  Model: {self.model} on :{self.port}")
            else:
                self.switch_mode(arg)
            return True

        elif command in ("/quit", "/exit", "/q"):
            print("  Exiting.")
            sys.exit(0)

        return False

    def run(self):
        """Main interactive loop."""
        # If an initial prompt template was loaded, inform the user
        if self.initial_prompt:
            content = load_prompt(self.initial_prompt)
            if content:
                self.messages.append({"role": "user", "content": content})
                print(f"  Loaded prompt template: {self.initial_prompt}")
                print(f"  Context injected. Type your question.\n")
            else:
                print(f"  Warning: prompt '{self.initial_prompt}' not found.")
                print(f"  Available: {', '.join(list_prompts())}\n")

        while True:
            try:
                user_input = input("\033[1;32magent>\033[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Exiting.")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                if self.handle_command(user_input):
                    continue

            response = self.chat(user_input)
            print(f"\n{response}\n")


# --- Entry point ---


def main():
    parser = argparse.ArgumentParser(
        description="Red Team ReAct Agent — interactive offensive security assistant",
    )
    parser.add_argument(
        "--mode",
        choices=["plan", "exec"],
        default="plan",
        help="Agent mode: plan (strategic) or exec (tactical)",
    )
    parser.add_argument(
        "--prompt",
        help="Load a prompt template by name at startup",
    )
    parser.add_argument(
        "--list-prompts",
        action="store_true",
        help="List available prompt templates and exit",
    )
    args = parser.parse_args()

    if args.list_prompts:
        templates = list_prompts()
        if templates:
            print("Available prompt templates:")
            for t in templates:
                print(f"  - {t}")
        else:
            print("No prompt templates found.")
        return

    print("=" * 60)
    print("  Red Team Agent")
    print("=" * 60)

    agent = RedTeamAgent(mode=args.mode, initial_prompt=args.prompt)
    agent.run()


if __name__ == "__main__":
    main()
