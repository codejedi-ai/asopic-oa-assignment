#!/usr/bin/env python3
"""
App Wrapper for Service 2 - WebSocket Server for Two-Way Communication with Service 1

This wrapper:
1. Exposes a WebSocket server for real-time bidirectional communication
2. Captures and streams all logs, screenshots, and model invocations to Service 1
3. Allows Service 1 to send commands to control the navigation agent
"""

import asyncio
import base64
import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import io
import os

# Add service-2 to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import uvicorn
from pydantic import BaseModel

# Import the Navigator from the existing navigate.py
from navigate import Navigator
import config
import mission_store


# ============================================================================
# Event Types for WebSocket Communication
# ============================================================================

class EventType(str, Enum):
    # Connection events
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    
    # Log events
    LOG = "log"
    
    # Navigation events
    NAVIGATION_START = "navigation_start"
    NAVIGATION_STEP = "navigation_step"
    NAVIGATION_COMPLETE = "navigation_complete"
    NAVIGATION_ERROR = "navigation_error"
    
    # Screenshot events
    SCREENSHOT = "screenshot"
    
    # Model invocation events
    MODEL_INVOKE_START = "model_invoke_start"
    MODEL_INVOKE_COMPLETE = "model_invoke_complete"
    
    # DOM events
    DOM_UPDATE = "dom_update"
    CANDIDATES_FOUND = "candidates_found"
    
    # Action events
    ACTION_EXECUTE = "action_execute"
    ACTION_RESULT = "action_result"
    
    # Goal events
    GOAL_CHECK = "goal_check"
    GOAL_REACHED = "goal_reached"


@dataclass
class WebSocketEvent:
    """Structured event for WebSocket communication"""
    type: EventType
    data: Dict[str, Any]
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value if isinstance(self.type, EventType) else self.type,
            "data": self.data,
            "timestamp": self.timestamp
        })


# ============================================================================
# Connection Manager for WebSocket clients
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        print(f"[WS] Client connected. Total connections: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        print(f"[WS] Client disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, event: WebSocketEvent):
        """Broadcast event to all connected clients"""
        if not self.active_connections:
            return
        
        message = event.to_json()
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f"[WS] Error sending to client: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            await self.disconnect(conn)
    
    async def send_to(self, websocket: WebSocket, event: WebSocketEvent):
        """Send event to a specific client"""
        try:
            await websocket.send_text(event.to_json())
        except Exception as e:
            print(f"[WS] Error sending to client: {e}")


# Global connection manager
manager = ConnectionManager()


# ============================================================================
# Streaming Logger - Captures and broadcasts logs
# ============================================================================

class StreamingLogger(logging.Handler):
    """Custom logging handler that broadcasts logs via WebSocket"""
    
    def __init__(self, connection_manager: ConnectionManager):
        super().__init__()
        self.manager = connection_manager
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
    
    def emit(self, record: logging.LogRecord):
        try:
            log_entry = self.format(record)
            event = WebSocketEvent(
                type=EventType.LOG,
                data={
                    "level": record.levelname,
                    "message": log_entry,
                    "logger": record.name,
                    "module": record.module,
                    "funcName": record.funcName,
                    "lineno": record.lineno
                }
            )
            
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.manager.broadcast(event),
                    self._loop
                )
        except Exception:
            self.handleError(record)


# ============================================================================
# Instrumented Navigator - Wraps Navigator with event broadcasting
# ============================================================================

class InstrumentedNavigator:
    """
    Wraps the Navigator class to broadcast events during navigation.
    This keeps the original Navigator intact while adding streaming capabilities.
    """
    
    def __init__(self, vision_model: str, connection_manager: ConnectionManager):
        self.navigator = Navigator(vision_model=vision_model)
        self.manager = connection_manager
        self._original_print = print
        self.logger: Optional[mission_store.MissionLogger] = None

    async def _broadcast(self, event_type: EventType, data: Dict[str, Any]):
        """Helper to broadcast events (and persist them to the mission log)."""
        event = WebSocketEvent(type=event_type, data=data)
        await self.manager.broadcast(event)
        # Persist every event to the mission log, but never write raw base64
        # screenshots into events.jsonl (the PNGs are saved as files instead).
        if self.logger:
            etype = event_type.value if isinstance(event_type, EventType) else str(event_type)
            if etype == EventType.SCREENSHOT.value:
                data = {k: v for k, v in data.items() if k != "screenshot_base64"}
            self.logger.log_event(etype, data)
    
    async def _capture_print(self, *args, **kwargs):
        """Capture print statements and broadcast as logs"""
        message = " ".join(str(arg) for arg in args)
        self._original_print(*args, **kwargs)
        await self._broadcast(EventType.LOG, {"message": message, "level": "INFO"})
    
    async def setup(self):
        """Setup the navigator and broadcast connection event"""
        await self.navigator.setup()
        await self._broadcast(EventType.CONNECTED, {"status": "Navigator initialized"})
    
    async def run_heuristic_search(self, start_url: str, repo_name: str, final_goal: str,
                                   mission_id: str = None) -> Dict[str, Any]:
        """
        Instrumented version of run_heuristic_search that broadcasts events.
        """
        # Resolve the repository from the goal via web search when it isn't
        # explicitly provided (e.g. "latest pytorch release" -> pytorch/pytorch),
        # instead of defaulting to a hardcoded repo.
        if not repo_name or repo_name in ("unknown",) or "/" not in repo_name:
            await self._broadcast(EventType.MODEL_INVOKE_START, {
                "model": "web_search",
                "purpose": "Finding the GitHub repository for your request"
            })
            resolved = await self.navigator.vision.resolve_repository(final_goal)
            if resolved:
                repo_name = resolved
                start_url = f"https://github.com/{resolved}"
                await self._broadcast(EventType.MODEL_INVOKE_COMPLETE, {
                    "model": "web_search",
                    "result": {"reasoning": f"Found repository: {resolved}"}
                })
            else:
                await self._broadcast(EventType.LOG, {
                    "level": "WARNING",
                    "message": "Could not resolve a repository from the request; using the provided URL."
                })

        # Open a persistent mission log under ~/.clio/missions/<id>/
        if mission_id:
            try:
                self.logger = mission_store.MissionLogger(mission_id, repo_name, final_goal, start_url)
            except Exception as e:
                print(f"[mission_store] could not open mission log: {e}")
                self.logger = None

        await self._broadcast(EventType.NAVIGATION_START, {
            "start_url": start_url,
            "repo_name": repo_name,
            "goal": final_goal
        })

        # SAS' transition bookkeeping
        pending_state = None
        pending_action = None

        try:
            # Initialize
            await self.navigator.client.call_tool("navigate_to_url", {"url": start_url})
            current_url = start_url

            # RL Initialization
            self.navigator.trajectory = []
            self.navigator.last_state_key = None
            
            # 0. Generate Prediction Model
            await self._broadcast(EventType.MODEL_INVOKE_START, {
                "model": "prediction_model",
                "purpose": "Generating weighted bag of words for goal"
            })
            
            self.navigator.cost_manager.add_cost("think", "Generating Prediction Model")
            self.navigator.prediction_model = await self.navigator.vision.generate_prediction_model(final_goal, repo_name)
            
            await self._broadcast(EventType.MODEL_INVOKE_COMPLETE, {
                "model": "prediction_model",
                "result": self.navigator.prediction_model
            })
            
            for step in range(1, 15):
                await self._broadcast(EventType.NAVIGATION_STEP, {
                    "step": step,
                    "current_url": current_url
                })
                
                # 1. Observe Current State
                self.navigator.cost_manager.add_cost("see", "Observing current state")
                state = await self.navigator.client.call_tool("get_page_state", {"include_screenshot": True})
                current_url = state.get("url", "")
                screenshot_data = state.get("screenshot_base64", "")
                
                # Broadcast screenshot
                if screenshot_data:
                    await self._broadcast(EventType.SCREENSHOT, {
                        "step": step,
                        "url": current_url,
                        "screenshot_base64": screenshot_data
                    })
                
                # Get Clean DOM
                dom_res = await self.navigator.client.call_tool("get_clean_dom_tree", {"include_attributes": True, "semantic_only": True})
                dom_tree = dom_res.get("dom_tree", "")
                await self.navigator.cache_dom(current_url, dom_tree)
                
                await self._broadcast(EventType.DOM_UPDATE, {
                    "step": step,
                    "dom_preview": dom_tree[:1000] if dom_tree else ""
                })

                # Persist this step's state S = (screenshot id, url, DOM) and close
                # out any pending transition from the previous action: S, A -> S'.
                current_state = None
                if self.logger:
                    current_state = self.logger.save_state(step, current_url, screenshot_data, dom_tree)
                    if pending_state is not None and pending_action is not None:
                        self.logger.record_transition(pending_state, pending_action, current_state)
                        pending_state, pending_action = None, None

                # 2. Check Goal State
                await self._broadcast(EventType.GOAL_CHECK, {
                    "step": step,
                    "checking": True
                })
                
                await self._broadcast(EventType.MODEL_INVOKE_START, {
                    "model": "vision",
                    "purpose": "Checking if goal is reached"
                })
                
                self.navigator.cost_manager.add_cost("think", "Checking if goal reached")
                goal_check = await self.navigator.vision.is_goal_reached(screenshot_data, current_url, dom_tree, repo_name)
                
                await self._broadcast(EventType.MODEL_INVOKE_COMPLETE, {
                    "model": "vision",
                    "result": goal_check
                })
                
                if goal_check.get("goal_reached"):
                    await self._broadcast(EventType.GOAL_REACHED, {
                        "step": step,
                        "reasoning": goal_check.get("reasoning")
                    })
                    
                    # Reward backpropagation
                    for experience in self.navigator.trajectory:
                        self.navigator.brain.update(experience["state"], experience["action"], 1.0)
                    
                    # Final extraction
                    await self._broadcast(EventType.MODEL_INVOKE_START, {
                        "model": "vision",
                        "purpose": "Final extraction of release data"
                    })
                    
                    self.navigator.cost_manager.add_cost("see", "Final Extraction")
                    html_content = state.get("html", "")
                    data = await self.navigator.vision.extract_with_vision_and_html(
                        screenshot_data,
                        html_content[:50000]
                    )
                    
                    await self._broadcast(EventType.MODEL_INVOKE_COMPLETE, {
                        "model": "vision",
                        "result": data
                    })
                    
                    await self._broadcast(EventType.NAVIGATION_COMPLETE, {
                        "success": True,
                        "result": data,
                        "total_cost": self.navigator.cost_manager.total_cost
                    })

                    if self.logger:
                        if pending_state is not None and pending_action is not None and current_state is not None:
                            self.logger.record_transition(pending_state, pending_action, current_state, reward=1.0)
                        self.logger.finish("success", data)

                    return data
                
                # 3. Lesser A* Search
                await self._broadcast(EventType.LOG, {
                    "level": "INFO",
                    "message": "Running Lesser A* Search (DOM Searcher)"
                })
                
                self.navigator.cost_manager.add_cost("lesser_astar", "DOM Searcher: finding candidates")
                candidates = await self.navigator.lesser_astar_search(
                    query_selector="a, button, summary",
                    weights=self.navigator.prediction_model.get("weights", {})
                )
                
                await self._broadcast(EventType.CANDIDATES_FOUND, {
                    "step": step,
                    "count": len(candidates),
                    "top_candidates": candidates[:10]  # Top 10 for display
                })
                
                # 4. Greater A* Search
                await self._broadcast(EventType.LOG, {
                    "level": "INFO",
                    "message": f"Running Greater A* Search on {len(candidates)} candidates"
                })
                
                self.navigator.cost_manager.add_cost("greater_astar", f"Page Searcher: scoring {len(candidates)} candidates")
                scored_candidates = await self.navigator.greater_astar_search(
                    candidates=candidates,
                    current_url=current_url,
                    prediction_model=self.navigator.prediction_model
                )
                
                if not scored_candidates:
                    await self._broadcast(EventType.LOG, {
                        "level": "WARNING",
                        "message": "No scored candidates found"
                    })
                    break
                
                best_node = max(scored_candidates, key=lambda x: x.get("final_score", 0))
                score = best_node.get("final_score", 0)
                target_url = best_node.get("url", "")
                
                await self._broadcast(EventType.LOG, {
                    "level": "INFO",
                    "message": f"Best candidate: '{best_node.get('text', '')[:50]}' (Score: {score:.2f})"
                })
                
                if score > 0.5:
                    target_href = best_node.get('url', '')
                    element_tag = best_node.get('tag', '').lower()
                    is_nav = bool(target_href and target_href.startswith(('http', '/')))

                    if not is_nav and element_tag not in ('button', 'input', 'summary', 'a'):
                        await self._broadcast(EventType.LOG, {
                            "level": "WARNING",
                            "message": f"Skipping non-clickable element: {element_tag}"
                        })
                        continue

                    # The browser is a single action tool: build the JSON action
                    # (reproducible: which element, on which page) and hand it over.
                    action_json = {
                        "type": "navigate" if is_nav else "click",
                        "selector": best_node.get("selector", ""),
                        "text": best_node.get("text", "")[:120],
                        "tag": element_tag,
                        "url": target_href,
                        "page_url": current_url,
                        "score": score,
                    }
                    if self.logger and current_state is not None:
                        pending_state = current_state
                        pending_action = action_json

                    await self._broadcast(EventType.ACTION_EXECUTE, {
                        "step": step,
                        "action_type": action_json["type"],
                        "target": best_node.get('text', '')[:50],
                        "tag": element_tag,
                        "score": score
                    })

                    self.navigator.trajectory.append({
                        "state": self.navigator.last_state_key,
                        "action": f"{action_json['type']}:{best_node.get('text', '')[:50]}",
                    })
                    self.navigator.cost_manager.add_cost(
                        action_json["type"], f"{action_json['type']} {best_node.get('text', '')[:50]}")

                    # One tool call: the browser channel performs the action and
                    # closes unused tabs (saving their URLs for later reference).
                    result = await self.navigator.client.act(action_json)

                    if result.get("closed_tabs"):
                        await self._broadcast(EventType.LOG, {
                            "level": "INFO",
                            "message": f"Closed {len(result['closed_tabs'])} unused tab(s); URLs saved for reference."
                        })

                    await self._broadcast(EventType.ACTION_RESULT, {
                        "step": step,
                        "success": result.get("ok", False),
                        "action": action_json["type"],
                        "error": result.get("error"),
                        "closed_tabs": result.get("closed_tabs", []),
                    })
                    if not result.get("ok"):
                        continue

                    await asyncio.sleep(2)
                else:
                    await self._broadcast(EventType.LOG, {
                        "level": "WARNING",
                        "message": "No nodes satisfy threshold (>0.5). Search halted."
                    })
                    break
            
            await self._broadcast(EventType.NAVIGATION_COMPLETE, {
                "success": False,
                "reason": "Max steps reached",
                "total_cost": self.navigator.cost_manager.total_cost
            })
            if self.logger:
                self.logger.finish("failed", {})
            return {}

        except Exception as e:
            error_msg = traceback.format_exc()
            await self._broadcast(EventType.NAVIGATION_ERROR, {
                "error": str(e),
                "traceback": error_msg
            })
            if self.logger:
                self.logger.finish("failed", {"error": str(e)})
            raise
    
    async def cleanup(self):
        """Cleanup navigator resources"""
        await self.navigator.cleanup()
        await self._broadcast(EventType.DISCONNECTED, {"status": "Navigator cleaned up"})


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Darci Navigation Service",
    description="Two-way WebSocket communication service for browser navigation agent",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models
class NavigationRequest(BaseModel):
    url: str
    repo: Optional[str] = None
    goal: Optional[str] = None
    mission_id: Optional[str] = None


class NavigationResponse(BaseModel):
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None


# Active navigation task
active_task: Optional[asyncio.Task] = None
instrumented_navigator: Optional[InstrumentedNavigator] = None


async def _cleanup_previous_navigator():
    """Tear down the previous mission's browser + MCP subprocess before starting a
    new one, so Chromium/MCP processes don't pile up across missions."""
    global instrumented_navigator
    if instrumented_navigator is not None:
        try:
            await instrumented_navigator.cleanup()
        except Exception as e:
            print(f"[cleanup] previous navigator cleanup failed: {e}")
        finally:
            instrumented_navigator = None


@app.get("/")
async def root():
    return {"status": "ok", "service": "Darci Navigation Service", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy", "connections": len(manager.active_connections)}


@app.get("/missions")
async def get_missions():
    """List all persisted missions (newest first) from ~/.clio/missions."""
    return {"missions": mission_store.list_missions()}


@app.get("/missions/{mission_id}")
async def get_mission_detail(mission_id: str):
    """Full mission log: metadata, event stream, and SAS' transitions."""
    data = mission_store.get_mission(mission_id)
    if data is None:
        return JSONResponse(status_code=404, content={"error": "mission not found"})
    return data


@app.get("/missions/{mission_id}/screenshot/{screenshot_id}")
async def get_mission_screenshot(mission_id: str, screenshot_id: str):
    """Serve a persisted screenshot PNG for a mission step."""
    path = mission_store.get_screenshot_path(mission_id, screenshot_id)
    if path is None:
        return JSONResponse(status_code=404, content={"error": "screenshot not found"})
    return FileResponse(str(path), media_type="image/png")


class RenameRequest(BaseModel):
    title: str


@app.post("/missions/{mission_id}/rename")
async def rename_mission_endpoint(mission_id: str, req: RenameRequest):
    """Rename a persisted mission."""
    if not mission_store.rename_mission(mission_id, req.title):
        return JSONResponse(status_code=404, content={"error": "mission not found"})
    return {"status": "ok"}


@app.post("/navigate")
async def start_navigation(request: NavigationRequest):
    """Start a navigation task via HTTP (results streamed via WebSocket)"""
    global active_task, instrumented_navigator
    
    if active_task and not active_task.done():
        return JSONResponse(
            status_code=409,
            content={"error": "Navigation already in progress"}
        )
    
    try:
        await _cleanup_previous_navigator()
        instrumented_navigator = InstrumentedNavigator(
            vision_model=config.VISION_MODEL,
            connection_manager=manager
        )
        await instrumented_navigator.setup()

        # Determine goal and repo
        repo = request.repo or "unknown"
        goal = request.goal or f"Find latest release for {repo}"
        
        # Start navigation task
        active_task = asyncio.create_task(
            instrumented_navigator.run_heuristic_search(
                start_url=request.url,
                repo_name=repo,
                final_goal=goal,
                mission_id=request.mission_id
            )
        )

        return {"status": "started", "message": "Navigation started. Connect via WebSocket for updates."}
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.post("/stop")
async def stop_navigation():
    """Stop current navigation task"""
    global active_task, instrumented_navigator
    
    if active_task and not active_task.done():
        active_task.cancel()
        try:
            await active_task
        except asyncio.CancelledError:
            pass
    
    if instrumented_navigator:
        await instrumented_navigator.cleanup()
        instrumented_navigator = None
    
    return {"status": "stopped", "message": "Navigation stopped"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time bidirectional communication.
    
    Client -> Server messages:
    - {"type": "navigate", "url": "...", "repo": "...", "goal": "..."}
    - {"type": "stop"}
    - {"type": "ping"}
    
    Server -> Client messages:
    - All EventType events (logs, screenshots, model invocations, etc.)
    """
    global active_task, instrumented_navigator
    
    await manager.connect(websocket)
    
    # Send welcome message
    await manager.send_to(websocket, WebSocketEvent(
        type=EventType.CONNECTED,
        data={"message": "Connected to Darci Navigation Service"}
    ))
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                msg_type = message.get("type", "")
                
                if msg_type == "ping":
                    await manager.send_to(websocket, WebSocketEvent(
                        type=EventType.LOG,
                        data={"message": "pong", "level": "DEBUG"}
                    ))
                
                elif msg_type == "navigate":
                    if active_task and not active_task.done():
                        await manager.send_to(websocket, WebSocketEvent(
                            type=EventType.ERROR,
                            data={"message": "Navigation already in progress"}
                        ))
                        continue
                    
                    url = message.get("url", "")
                    repo = message.get("repo", "unknown")
                    goal = message.get("goal", f"Find latest release for {repo}")
                    mission_id = message.get("mission_id")

                    if not url:
                        await manager.send_to(websocket, WebSocketEvent(
                            type=EventType.ERROR,
                            data={"message": "URL is required"}
                        ))
                        continue
                    
                    # Start navigation (tear down any previous browser/MCP first)
                    await _cleanup_previous_navigator()
                    instrumented_navigator = InstrumentedNavigator(
                        vision_model=config.VISION_MODEL,
                        connection_manager=manager
                    )
                    await instrumented_navigator.setup()
                    
                    active_task = asyncio.create_task(
                        instrumented_navigator.run_heuristic_search(
                            start_url=url,
                            repo_name=repo,
                            final_goal=goal,
                            mission_id=mission_id
                        )
                    )
                
                elif msg_type == "stop":
                    if active_task and not active_task.done():
                        active_task.cancel()
                        try:
                            await active_task
                        except asyncio.CancelledError:
                            pass
                    
                    if instrumented_navigator:
                        await instrumented_navigator.cleanup()
                        instrumented_navigator = None
                    
                    await manager.send_to(websocket, WebSocketEvent(
                        type=EventType.LOG,
                        data={"message": "Navigation stopped", "level": "INFO"}
                    ))
                
                else:
                    await manager.send_to(websocket, WebSocketEvent(
                        type=EventType.ERROR,
                        data={"message": f"Unknown message type: {msg_type}"}
                    ))
                    
            except json.JSONDecodeError:
                await manager.send_to(websocket, WebSocketEvent(
                    type=EventType.ERROR,
                    data={"message": "Invalid JSON message"}
                ))
                
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Error: {e}")
        await manager.disconnect(websocket)


# ============================================================================
# HTTP fallback for legacy support (matches current service-1 expectations)
# ============================================================================

@app.post("/")
async def legacy_endpoint(request: dict):
    """Legacy HTTP endpoint for backwards compatibility with service-1"""
    messages = request.get("messages", [])
    if not messages:
        return {"response": "No message provided"}
    
    message = messages[0] if isinstance(messages, list) else str(messages)
    
    # Parse the message to extract navigation intent
    # For now, return a simple response
    return {
        "response": f"Navigation service received: {message}. Connect via WebSocket at /ws for real-time updates."
    }


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Darci Navigation Service - App Wrapper")
    print("=" * 60)
    print("\nEndpoints:")
    print("  - HTTP:     http://localhost:8000/")
    print("  - WebSocket: ws://localhost:8000/ws")
    print("\nAPI Docs: http://localhost:8000/docs")
    print("=" * 60)
    
    uvicorn.run(
        "app_wrapper:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
