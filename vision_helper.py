"""
Vision model integration for navigation and extraction
"""

import json
import os
import base64
from typing import Dict, Any, Optional
from openai import AsyncOpenAI
import config
from pathlib import Path
from prompts import NavigationPrompts

class VisionAssistant:
    def __init__(self, vision_model: str = None):
        if vision_model:
            config.VISION_MODEL = vision_model
            
        self.openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        try:
            from anthropic import AsyncAnthropic
            self.anthropic_client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
        except ImportError:
            self.anthropic_client = None
            print("Anthropic client not initialized (package might be missing)")
            
        self.strategy_model = config.STRATEGY_MODEL # This is usually Claude
        self.tagging_model = vision_model if vision_model else config.TAGGING_MODEL # This is the Vision model (GPT-4o)
        self.tagging_model = config.TAGGING_MODEL
        self.max_tokens = 1000
        
    async def get_navigation_instruction(self, screenshot_data: str, 
                                        current_url: str, 
                                        step_name: str,
                                        goal: str = None) -> Optional[Dict[str, Any]]:
        """Get navigation instruction from vision model"""
        
        system_prompt = NavigationPrompts.navigation_system_prompt()
        
        # Default behavior if no specific goal provided (fallback to original task)
        task_context = """
        1. If at GitHub homepage: Find and use the search bar
        2. If at search results: Click on the correct repository
        3. If at repository page: Find and click the "Releases" link/tab
        4. If at releases page: Extract the latest release information
        """
        
        if goal:
            task_context = f"GOAL: {goal}\n\nDetermine the next logical step to achieve this goal."

        user_prompt = NavigationPrompts.navigation_user_prompt(current_url, step_name, task_context)
        
        try:
            if "claude" in self.strategy_model and self.anthropic_client:
                response = await self.anthropic_client.messages.create(
                    model=self.strategy_model,
                    max_tokens=self.max_tokens,
                    temperature=0.1,
                    system=system_prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": screenshot_data
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": user_prompt
                                }
                            ]
                        }
                    ]
                )
                content = response.content[0].text
            else:
                # Fallback or if strategy model is OpenAI
                response = await self.openai_client.chat.completions.create(
                    model=self.strategy_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{screenshot_data}"
                            }}
                        ]}
                    ],
                    max_tokens=self.max_tokens,
                    temperature=0.1
                )
                content = response.choices[0].message.content
            
            # Clean response (remove markdown code blocks)
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
            
        except Exception as e:
            print(f"Error getting navigation instruction: {e}")
            return None
    
    async def calculate_link_heuristics(self, candidates: list, repo: str, screenshot_data: str = None, dom_tree: str = None) -> list:
        """Eyes report to Brain, Brain calculates heuristics
        
        Flow: Eyes (GPT-4o) → Brain (Claude) → Returns scores for A*
        
        Args:
            candidates: List of dicts with keys: url, text, depth, discovery_count
            repo: Repository name (e.g., 'openclaw/openclaw')
            screenshot_data: Base64 encoded screenshot (for Eyes)
            dom_tree: HTML DOM snippet (for Brain's analysis)
            
        Returns:
            List of candidates with added 'heuristic_value' key
        """
        
        if not candidates:
            return []
        
        # STEP 1: Eyes (GPT-4o) describe what they see
        visual_description = ""
        if screenshot_data:
            try:
                print("   -> Eyes (GPT-4o) analyzing page visually...")
                eyes_prompt = NavigationPrompts.eyes_analysis_prompt()

                response = await self.openai_client.chat.completions.create(
                    model=self.tagging_model,
                    messages=[
                        {"role": "system", "content": "You are the Eyes of a web navigation system. Describe what you see clearly and concisely."},
                        {"role": "user", "content": [
                            {"type": "text", "text": eyes_prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{screenshot_data}"
                            }}
                        ]}
                    ],
                    max_tokens=500,
                    temperature=0.1
                )
                visual_description = response.choices[0].message.content
                print(f"   -> Eyes report: {visual_description[:150]}...")
            except Exception as e:
                print(f"   -> Eyes failed to analyze: {e}")
                visual_description = "Visual analysis unavailable."
        
        # STEP 2: Prepare link candidates for Brain
        candidate_summary = []
        for i, cand in enumerate(candidates):
            candidate_summary.append({
                "index": i,
                "url": cand["url"],
                "text": cand["text"][:100],
            })
        
        # STEP 3: Brain (Claude) scores links using Eyes' report + DOM + candidates
        # STEP 3: Brain (Claude) scores links using Eyes' report + DOM + candidates
        brain_system_prompt = NavigationPrompts.brain_heuristic_system_prompt(repo)
        
        brain_user_prompt = NavigationPrompts.brain_heuristic_user_prompt(
            visual_description, dom_tree, candidates, repo
        )

        try:
            print(f"   -> Brain (Claude) reasoning about {len(candidates)} links...")
            
            # Use Claude (Brain) for strategic reasoning
            if "claude" in self.strategy_model and self.anthropic_client:
                response = await self.anthropic_client.messages.create(
                    model=self.strategy_model,
                    max_tokens=3000,
                    temperature=0.1,
                    system=brain_system_prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": brain_user_prompt
                        }
                    ]
                )
                content = response.content[0].text
            else:
                # Fallback to OpenAI if Claude not available
                response = await self.openai_client.chat.completions.create(
                    model=self.strategy_model,
                    messages=[
                        {"role": "system", "content": brain_system_prompt},
                        {"role": "user", "content": brain_user_prompt}
                    ],
                    max_tokens=3000,
                    temperature=0.1
                )
                content = response.choices[0].message.content
            
            # Parse Brain's response
            content = content.replace('```json', '').replace('```', '').strip()
            scores = json.loads(content)
            
            # Merge scores back into candidates
            score_map = {s["index"]: s["heuristic_value"] for s in scores}
            for i, cand in enumerate(candidates):
                cand["heuristic_value"] = score_map.get(i, 0)
            
            return candidates
            
        except Exception as e:
            print(f"   -> Brain reasoning failed: {e}")
            # Fallback: return candidates with default score
            for cand in candidates:
                cand["heuristic_value"] = 50
            return candidates
    
    async def is_goal_reached(self, screenshot_data: str, url: str, dom_tree: str, repo: str) -> dict:
        """Brain decides if the current page has reached the goal (latest release info)
        
        Returns:
            {
                "goal_reached": true/false,
                "confidence": 0-100,
                "reasoning": "explanation"
            }
        """
        
        if screenshot_data:
            try:
                eyes_prompt = NavigationPrompts.eyes_goal_check_prompt()

                response = await self.openai_client.chat.completions.create(
                    model=self.tagging_model,
                    messages=[
                        {"role": "system", "content": "You are the Eyes. Describe what you see."},
                        {"role": "user", "content": [
                            {"type": "text", "text": eyes_prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{screenshot_data}"
                            }}
                        ]}
                    ],
                    max_tokens=300,
                    temperature=0.1
                )
                visual_description = response.choices[0].message.content
            except Exception as e:
                print(f"   -> Eyes failed: {e}")
                visual_description = "Visual unavailable"
        
        # Brain decides
        brain_prompt = f"""**Mission**: Find the LATEST release page for repository '{repo}'.

**Current URL**: {url}

**Eyes' Report**:
{visual_description}

**DOM Snippet**:
{dom_tree[:2000]}

**Decision Required**: Has the goal been reached?

Evaluate:
1. Is this a /releases/tag/ page?
2. Does it show "Latest" badge/indicator?
3. Is this clearly the most recent release?

Return JSON:
{{
    "goal_reached": true/false,
    "confidence": 0-100,
    "reasoning": "brief explanation"
}}"""

        try:
            if "claude" in self.strategy_model and self.anthropic_client:
                response = await self.anthropic_client.messages.create(
                    model=self.strategy_model,
                    max_tokens=500,
                    temperature=0.1,
                    system="You are the Brain deciding if the navigation goal is reached.",
                    messages=[{"role": "user", "content": brain_prompt}]
                )
                content = response.content[0].text
            else:
                response = await self.openai_client.chat.completions.create(
                    model=self.strategy_model,
                    messages=[
                        {"role": "system", "content": "You are the Brain deciding if the navigation goal is reached."},
                        {"role": "user", "content": brain_prompt}
                    ],
                    max_tokens=500,
                    temperature=0.1
                )
                content = response.choices[0].message.content
            
            content = content.replace('```json', '').replace('```', '').strip()
            result = json.loads(content)
            return result
            
        except Exception as e:
            print(f"   -> Brain goal check failed: {e}")
            return {"goal_reached": False, "confidence": 0, "reasoning": "Error in evaluation"}
    
    
    
    async def extract_release_info(self, screenshot_data: str) -> Optional[Dict[str, Any]]:
        """Extract release information from screenshot"""
        
        # This fallback method just uses the generic prompt
        prompt = NavigationPrompts.extraction_prompt(["version", "commit", "author"])
        
        try:
            if "claude" in self.model:
                from anthropic import AsyncAnthropic
                client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
                
                response = await client.messages.create(
                    model=self.model,
                    max_tokens=1500,
                    temperature=0.1,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": screenshot_data
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ]
                )
                content = response.content[0].text
            else:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{screenshot_data}"
                            }}
                        ]}
                    ],
                    max_tokens=1500,
                    temperature=0.1
                )
                content = response.choices[0].message.content
            
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
            
        except Exception as e:
            print(f"Error extracting release info: {e}")
            return {"version": "", "tag": "", "author": ""}
    async def extract_release_info_from_html(self, html_content: str) -> Dict[str, Any]:
        """Extract release information from HTML using the model"""
        
    async def extract_release_info_from_html(self, html_content: str) -> Dict[str, Any]:
        """Extract release information from HTML using the model"""
        
        system_prompt = NavigationPrompts.extraction_system_prompt()
        prompt = NavigationPrompts.extraction_prompt(["version", "commit", "author"])
        
        try:
            if "claude" in self.model:
                from anthropic import AsyncAnthropic
                client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
                
                response = await client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    temperature=0.1,
                    system=system_prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"{prompt}\n\nHTML Content:\n{html_content}"
                                }
                            ]
                        }
                    ]
                )
                content = response.content[0].text
            else:
                # Fallback for OpenAI (might hit token limits if HTML is huge, but usually fine for newer models)
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"{prompt}\n\nHTML Content:\n{html_content}"}
                    ],
                    max_tokens=4000,
                    temperature=0.1
                )
                content = response.choices[0].message.content
            
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
            
        except Exception as e:
            print(f"Error extracting release info from HTML: {e}")
            return {"version": "", "tag": "", "author": "Error extracting"}
            
    async def generate_navigation_plan(self, goal: str, repo: str = None) -> list:
        """Generate a high-level navigation plan (list of steps) based on the goal"""
        
        system_prompt = "You are a Smart Navigation Planner. You understand URL structures (GitHub, etc.) and prefer direct navigation over clicking through UI."
        
        # Smart Logic: if we have a repo, jump straight to it
        if repo:
            prompt = f"""Goal: {goal}
            Context: Repository is known: '{repo}'
            
            Strategy:
            1. Navigate DIRECTLY to the releases page: https://github.com/{repo}/releases
            2. If specific version needed, find it. Otherwise, look at the latest.
            3. Extract information.
            
            Return valid JSON:
            {{
                "steps": [
                    "Navigate to https://github.com/{repo}/releases",
                    "Click on the latest release title to view details",
                    "Extract release information"
                ]
            }}
            """
        else:
            prompt = f"""Goal: {goal}
            
            Standard GitHub Release Flow (Reference):
            1. Navigate to GitHub homepage
            2. Search for the repository
            3. Click on the repository link
            4. Click on 'Releases'
            5. Click on the specific tag/title of the latest release (to view full details)
            6. Extract the release information
            
            Return valid JSON:
            {{
                "steps": [
                    "Step 1 description",
                    "Step 2 description",
                    ...
                ]
            }}
            """
        
        try:
            if "claude" in self.strategy_model and self.anthropic_client:
                response = await self.anthropic_client.messages.create(
                    model=self.strategy_model,
                    max_tokens=1000,
                    temperature=0.1,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}]
                )
                content = response.content[0].text
            else:
                response = await self.openai_client.chat.completions.create(
                    model=self.strategy_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1000,
                    temperature=0.1
                )
                content = response.choices[0].message.content
                
            content = content.replace('```json', '').replace('```', '').strip()
            plan = json.loads(content)
            return plan.get("steps", [])
            
        except Exception as e:
            print(f"Error generating plan: {e}")
            # Fallback plan
            return [
                "Navigate to https://github.com",
                f"Search for repository mentioned in '{goal}'",
                "Click on the repository link",
                "Click on 'Releases'",
                "Click on the latest release tag",
                "Extract release information"
            ]

    async def generate_prediction_model(self, goal: str, repo: str) -> Dict[str, Any]:
        """Ask Brain (Claude) to generate a Prediction Model (Weighted Bag of Words) for the Goal.
        Uses cache to avoid redundant API calls.
        """
        
        # --- CACHE CHECK ---
        cache_path = Path("data/prediction_cache.json")
        goal_lower = goal.lower()
        
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                    
                # Check if any cached model matches the goal keywords
                for model_key, model_data in cache.get("models", {}).items():
                    keywords = model_data.get("keywords", [])
                    if any(kw in goal_lower for kw in keywords):
                        print(f"   [Cache Hit] Using cached prediction model: '{model_key}'")
                        return {
                            "weights": model_data.get("weights", {}),
                            "decay_rate": model_data.get("decay_rate", 0.5)
                        }
            except Exception as e:
                print(f"   [Cache] Could not read cache: {e}")
        
        # --- NO CACHE HIT: Generate with Claude ---
        system_prompt = NavigationPrompts.prediction_model_system_prompt()
        user_prompt = NavigationPrompts.prediction_model_user_prompt(goal, repo)
        
        try:
            print(f"   -> Brain generating prediction model for: {goal[:50]}...")
            
            if "claude" in self.strategy_model and self.anthropic_client:
                 response = await self.anthropic_client.messages.create(
                    model=self.strategy_model,
                    max_tokens=1000,
                    temperature=0.1,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                 content = response.content[0].text
            else:
                 response = await self.openai_client.chat.completions.create(
                    model=self.strategy_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=1000,
                    temperature=0.1
                )
                 content = response.choices[0].message.content

            content = content.replace('```json', '').replace('```', '').strip()
            result = json.loads(content)
            
            # --- SAVE TO CACHE ---
            try:
                # Extract key from goal for caching
                cache_key = "_".join(goal_lower.split()[:3]).replace("/", "_")
                
                if cache_path.exists():
                    with open(cache_path, "r", encoding="utf-8") as f:
                        cache = json.load(f)
                else:
                    cache = {"description": "Cached Prediction Models", "models": {}}
                
                # Add to cache with keywords from goal
                cache["models"][cache_key] = {
                    "keywords": goal_lower.split()[:5],
                    "weights": result.get("weights", {}),
                    "decay_rate": result.get("decay_rate", 0.5)
                }
                
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(cache, f, indent=2)
                print(f"   [Cache] Saved new prediction model: '{cache_key}'")
            except Exception as e:
                print(f"   [Cache] Could not save to cache: {e}")
            
            return result
            
        except Exception as e:
            print(f"Error generating prediction model: {e}")
            # Fallback model
            return {
                "weights": {
                    "Releases": 1.0,
                    "Latest": 0.9,
                    "Download": 0.5
                },
                "decay_rate": 0.5
            }

    async def calculate_link_heuristics(self, candidates: list, repo: str, screenshot_data: str = None, dom_tree: str = None) -> list:
        # DEPRECATED: Replaced by local scoring in navigate.py using Prediction Model
        # But kept as fallback or for high-level semantic checks if needed.
        pass
            
    async def is_goal_reached(self, screenshot_data: str, url: str, dom_tree: str, repo: str) -> dict:
        """Brain decides if the current page has reached the goal (latest release info)
        
        Returns:
            {
                "goal_reached": true/false,
                "confidence": 0-100,
                "reasoning": "explanation"
            }
        """
        
        # Eyes first
        visual_description = ""
        if screenshot_data:
            try:
                eyes_prompt = """Describe this GitHub page. Focus on:
- Is this a release/tag page?
- Do you see "Latest" badge or indicator?
- What version/tag information is visible?
- Is this clearly the latest release page?"""

                response = await self.openai_client.chat.completions.create(
                    model=self.tagging_model,
                    messages=[
                        {"role": "system", "content": "You are the Eyes. Describe what you see."},
                        {"role": "user", "content": [
                            {"type": "text", "text": eyes_prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{screenshot_data}"
                            }}
                        ]}
                    ],
                    max_tokens=300,
                    temperature=0.1
                )
                visual_description = response.choices[0].message.content
            except Exception as e:
                print(f"   -> Eyes failed: {e}")
                visual_description = "Visual unavailable"
        
        # Brain decides
        brain_prompt = NavigationPrompts.brain_goal_check_prompt(repo, url, visual_description, dom_tree)
        system_msg = NavigationPrompts.brain_goal_check_system()

        try:
            if "claude" in self.strategy_model and self.anthropic_client:
                response = await self.anthropic_client.messages.create(
                    model=self.strategy_model,
                    max_tokens=500,
                    temperature=0.1,
                    system=system_msg,
                    messages=[{"role": "user", "content": brain_prompt}]
                )
                content = response.content[0].text
            else:
                response = await self.openai_client.chat.completions.create(
                    model=self.strategy_model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": brain_prompt}
                    ],
                    max_tokens=500,
                    temperature=0.1
                )
                content = response.choices[0].message.content
            
            content = content.replace('```json', '').replace('```', '').strip()
            result = json.loads(content)
            return result
            
        except Exception as e:
            print(f"   -> Brain goal check failed: {e}")
            return {"goal_reached": False, "confidence": 0, "reasoning": "Error in evaluation"}
    
    
    async def extract_with_vision_and_html(self, screenshot_data: str, html_content: str, extract_fields: list = None) -> Dict[str, Any]:
        """Extract information using both visual context and HTML.
        Prioritizes GPT (Vision) as requested for final extraction.
        """
        
    async def extract_with_vision_and_html(self, screenshot_data: str, html_content: str, extract_fields: list = None) -> Dict[str, Any]:
        """Extract information using both visual context and HTML.
        Prioritizes GPT (Vision) as requested for final extraction.
        """
        
        if extract_fields is None:
            extract_fields = ["version", "commit", "author"]
        
        system_prompt = NavigationPrompts.extraction_system_prompt()
        prompt = NavigationPrompts.extraction_prompt(extract_fields)
        
        try:
            # User explicit request: Use GPT Vision model over Claude for extraction
            # We use self.tagging_model which is configured as gpt-4o in config
            extraction_model = self.tagging_model 
            
            # Helper to run OpenAI extraction
            async def run_openai_extraction():
                response = await self.openai_client.chat.completions.create(
                    model=extraction_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": [
                                {"type": "text", "text": f"{prompt}\n\nHTML Content:\n{html_content}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_data}"}}
                        ]}
                    ],
                    max_tokens=4000
                )
                return response.choices[0].message.content

            # Helper to run Claude extraction 
            async def run_claude_extraction():
                response = await self.anthropic_client.messages.create(
                    model=self.strategy_model,
                    max_tokens=4000,
                    temperature=0.1,
                    system=system_prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": screenshot_data
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": f"{prompt}\n\nHTML Content:\n{html_content}"
                                }
                            ]
                        }
                    ]
                )
                return response.content[0].text

            content = ""
            # Prioritize OpenAI (GPT-4o) if available
            if self.openai_client and "gpt" in extraction_model:
                try:
                    print(f"   -> Extracting with {extraction_model} (Visual + HTML)...")
                    content = await run_openai_extraction()
                except Exception as gpt_error:
                    print(f"GPT extraction failed, trying fallback: {gpt_error}")
                    if self.anthropic_client:
                        content = await run_claude_extraction()
            elif self.anthropic_client:
                 print(f"   -> Extracting with {self.strategy_model} (Visual + HTML)...")
                 content = await run_claude_extraction()
            else:
                 # Last resort attempt with whatever client exists
                 content = await run_openai_extraction()
                
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
            
        except Exception as e:
            print(f"Error in combined extraction: {e}")
            return {}
            
    # Bonus: Natural language prompt processing
    async def process_natural_language_prompt(self, prompt: str, screenshot_data: str) -> Dict[str, Any]:
        """Process natural language prompts for flexible queries"""
        system_prompt = """You are a web navigation and information extraction assistant. 
        Process the user's natural language query and determine what actions are needed."""
        
        # Implementation for bonus challenge
        pass