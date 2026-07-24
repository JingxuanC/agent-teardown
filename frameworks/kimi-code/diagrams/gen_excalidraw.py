#!/usr/bin/env python3
"""
Generate hand-drawn style Excalidraw architecture diagrams for kimi-code teardown.

Output: .excalidraw files that open at https://excalidraw.com (File → Open).
The Excalidraw renderer natively produces the sketch/cartoon aesthetic — no
image generation API needed, and the files are fully editable.
"""
from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from typing import Literal

# ---------- Excalidraw element factory ----------

def _id() -> str:
    return str(uuid.uuid4())


def _common(x: float, y: float, stroke: str, bg: str) -> dict:
    return {
        "fillStyle": "hachure",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,                 # 1 = hand-drawn wobble
        "opacity": 100,
        "angle": 0,
        "x": x, "y": y,
        "strokeColor": stroke,
        "backgroundColor": bg,
        "seed": 1,
        "groupIds": [],
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
        "version": 1,
        "versionNonce": 1,
        "isDeleted": False,
    }


def rect(x: float, y: float, w: float, h: float, label: str,
         bg: str = "#fff8e1", stroke: str = "#f57c00") -> list[dict]:
    """A labelled rounded rectangle (a node on the diagram)."""
    rect_id = _id()
    text_id = _id()
    box = {
        **_common(x, y, stroke, bg),
        "type": "rectangle",
        "id": rect_id,
        "width": w, "height": h,
        "boundElements": [{"type": "text", "id": text_id}],
        "roundness": {"type": 3},
    }
    # naive width estimate — Excalidraw will re-fit on edit
    text_w = max(80, len(label) * 8)
    text_h = 24
    txt = {
        **_common(x + (w - text_w) / 2, y + (h - text_h) / 2, stroke, "transparent"),
        "type": "text",
        "id": text_id,
        "width": text_w, "height": text_h,
        "text": label,
        "fontSize": 18,
        "fontFamily": 1,                 # Virgil (hand-drawn)
        "textAlign": "center",
        "verticalAlign": "middle",
        "containerId": rect_id,
        "originalText": label,
        "lineHeight": 1.25,
        "strokeWidth": 1,
    }
    return [box, txt]


def arrow(x1: float, y1: float, x2: float, y2: float,
          stroke: str = "#757575", label: str | None = None) -> list[dict]:
    """A sketchy arrow from (x1,y1) to (x2,y2), with an optional label."""
    a_id = _id()
    arr = {
        **_common(x1, y1, stroke, "transparent"),
        "type": "arrow",
        "id": a_id,
        "width": x2 - x1, "height": y2 - y1,
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": "arrow",
    }
    if label is None:
        return [arr]
    text_id = _id()
    mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
    tw = max(40, len(label) * 7)
    txt = {
        **_common(mid_x - tw / 2, mid_y - 12, stroke, "transparent"),
        "type": "text", "id": text_id,
        "width": tw, "height": 20,
        "text": label, "fontSize": 14, "fontFamily": 1,
        "textAlign": "center", "verticalAlign": "middle",
        "containerId": None, "originalText": label, "lineHeight": 1.25,
        "strokeWidth": 1,
    }
    return [arr, txt]


def text(x: float, y: float, s: str, size: int = 22,
         stroke: str = "#212121", bold: bool = False) -> dict:
    tw = max(60, len(s) * (size * 0.55))
    return {
        **_common(x, y, stroke, "transparent"),
        "type": "text", "id": _id(),
        "width": tw, "height": size + 4,
        "text": s, "fontSize": size, "fontFamily": 1,
        "textAlign": "left", "verticalAlign": "top",
        "containerId": None, "originalText": s, "lineHeight": 1.25,
        "strokeWidth": 1,
    }


def save(path: str, elements: list[dict], title: str = "") -> None:
    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {
            "viewBackgroundColor": "#fafafa",
            "gridSize": 20,
        },
        "files": {},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"wrote {path}  ({len(elements)} elements)  {title}")


# ---------- Color palette (cheerful, hand-drawn friendly) ----------

BLUE   = ("#bbdefb", "#1565c0")     # bg, stroke
YELLOW = ("#fff9c4", "#f9a825")
GREEN  = ("#c8e6c9", "#2e7d32")
PINK   = ("#f8bbd0", "#ad1457")
PURPLE = ("#e1bee7", "#6a1b9a")
GRAY   = ("#eeeeee", "#616161")
ORANGE = ("#ffe0b2", "#e65100")
TEAL   = ("#b2dfdb", "#00695c")


# ---------- Diagram 1: Overall Layered Architecture ----------

def diagram_01_overall(path: str) -> None:
    e: list[dict] = []
    e += [text(80, 40, "kimi-code · Overall Architecture", size=32, bold=True)]
    e += [text(80, 90, "(apps → engine → foundation → persistence)", size=16, stroke="#757575")]

    # apps layer
    e += rect(80,  160, 200, 60, "TUI\n(terminal)", *BLUE)
    e += rect(320, 160, 200, 60, "Web UI\n(apps/kimi-web)", *BLUE)
    e += rect(560, 160, 200, 60, "IDE\n(Zed/JetBrains via ACP)", *BLUE)
    e += [text(80, 145, "User-facing apps", size=14, stroke="#1565c0")]

    # sdk + server
    e += rect(80, 280, 680, 50, "@moonshot-ai/klient  (SDK facade, zod-validated)", *YELLOW)
    e += rect(80, 360, 680, 50, "kap-server  (REST + WebSocket /api/v1)", *YELLOW)

    # engine
    e += [text(80, 445, "agent-core-v2 — the engine (Agent scope services)", size=14, stroke="#ad1457")]
    engine_y = 460
    labels = [("Loop", *PINK), ("Goal", *PINK), ("Swarm", *PINK),
              ("Subagent", *PINK), ("Tools", *PINK), ("Context", *PINK),
              ("Plan", *PINK), ("Skill", *PINK), ("MCP", *PINK)]
    for i, (lbl, bg, st) in enumerate(labels):
        col, row = i % 3, i // 3
        e += rect(80 + col * 230, engine_y + row * 80, 200, 60, lbl, bg, st)

    # foundation
    e += [text(80, 645, "Foundation", size=14, stroke="#6a1b9a")]
    e += rect(80,  660, 220, 60, "kosong\n(LLM abstraction)", *PURPLE)
    e += rect(320, 660, 220, 60, "Wire\n(Op/Model, event sourcing)", *PURPLE)
    e += rect(560, 660, 220, 60, "DI × Scope\n(App/Session/Agent)", *PURPLE)

    # persistence
    e += [text(80, 745, "Persistence (NodeFs backends)", size=14, stroke="#616161")]
    e += rect(80,  760, 220, 50, "wire.jsonl\n(append log)", *GRAY)
    e += rect(320, 760, 220, 50, "state.json\n(atomic doc)", *GRAY)
    e += rect(560, 760, 220, 50, "blobs/<sha256>\n(content-addressed)", *GRAY)

    # vertical connectors
    for x in [180, 420, 660]:
        e += arrow(x, 220, x, 275, stroke="#9e9e9e")
        e += arrow(x, 330, x, 355, stroke="#9e9e9e")
        e += arrow(x, 410, x, 455, stroke="#9e9e9e")

    # engine → foundation
    for x in [180, 420, 660]:
        e += arrow(x, 620, x, 655, stroke="#9e9e9e")
        e += arrow(x, 720, x, 755, stroke="#9e9e9e")

    save(path, e, "01-overall")


# ---------- Diagram 2: Agent Loop (Prompt → Turn → Step) ----------

def diagram_02_loop(path: str) -> None:
    e: list[dict] = []
    e += [text(60, 40, "Agent Loop · Prompt → Turn → Step", size=30, bold=True)]

    # three layers
    e += [text(60, 110, "1) Prompt layer  (who's asking?)", size=18, stroke="#1565c0")]
    e += rect(60,  140, 180, 60, "User message", *BLUE)
    e += rect(280, 140, 180, 60, "Goal continuation", *BLUE)
    e += rect(500, 140, 180, 60, "Cron fire", *BLUE)
    e += rect(720, 140, 180, 60, "Background task", *BLUE)

    e += [text(60, 240, "2) Turn layer  (lifecycle, single-threaded per agent)", size=18, stroke="#f57c00")]
    # turn state machine
    e += rect(60,  270, 130, 60, "queued", *YELLOW)
    e += rect(250, 270, 130, 60, "running", *GREEN)
    e += rect(440, 270, 130, 60, "completed", *GRAY)
    e += rect(630, 270, 130, 60, "cancelled", *GRAY)
    e += rect(820, 270, 130, 60, "failed", *PINK)
    e += arrow(190, 300, 245, 300, label="pump")
    e += arrow(380, 300, 435, 300, label="done")
    e += arrow(380, 300, 625, 300, label="abort")
    e += arrow(380, 300, 815, 300, label="error")

    e += [text(60, 380, "3) Step layer  (LLM call + tool execution loop)", size=18, stroke="#ad1457")]
    # step loop
    e += rect(60,  420, 160, 60, "Build context", *PINK)
    e += rect(280, 420, 160, 60, "Call LLM\n(kosong)", *PINK)
    e += rect(500, 420, 160, 60, "Tool calls?", *PINK)
    e += rect(720, 420, 180, 60, "Execute tools\n(parallel)", *PINK)

    e += arrow(220, 450, 275, 450)
    e += arrow(440, 450, 495, 450)
    e += arrow(660, 450, 715, 450, label="yes")
    # loop back
    e += arrow(810, 480, 810, 540, stroke="#9e9e9e")
    e += arrow(810, 540, 140, 540, stroke="#9e9e9e")
    e += arrow(140, 540, 140, 480, stroke="#9e9e9e", label="next step")
    # no tool calls → turn ends
    e += arrow(580, 480, 580, 580, stroke="#9e9e9e", label="no → turn ends")

    # steer sidebar
    e += [text(1000, 240, "Steer (user mid-turn input)", size=16, stroke="#00695c")]
    e += rect(1000, 270, 220, 70, "Buffer message\n→ flush at step boundary", *TEAL)
    e += arrow(1000, 305, 380, 305, stroke="#00695c", label="inject")

    # step retry sidebar
    e += [text(1000, 420, "StepRetry (on provider 429/5xx)", size=16, stroke="#6a1b9a")]
    e += rect(1000, 450, 220, 70, "Exponential backoff\nmax 5 attempts", *PURPLE)
    e += arrow(360, 450, 360, 420, stroke="#6a1b9a")
    e += arrow(360, 420, 995, 440, stroke="#6a1b9a")

    save(path, e, "02-loop")


# ---------- Diagram 3: Swarm + Subagent + Goal collaboration ----------

def diagram_03_multi_agent(path: str) -> None:
    e: list[dict] = []
    e += [text(60, 40, "Multi-Agent: Swarm vs Goal vs Subagent", size=28, bold=True)]
    e += [text(60, 80, "(parallel batch vs serial autonomous vs one-off delegation)", size=15, stroke="#757575")]

    # --- Swarm (fan-out / fan-in) ---
    e += [text(60, 140, "①  Swarm mode  (parallel batch, up to 128)", size=20, stroke="#1565c0")]
    e += rect(200, 170, 200, 60, "Main agent", *BLUE)
    e += rect(600, 130, 160, 50, "Subagent 1", *GREEN)
    e += rect(600, 200, 160, 50, "Subagent 2", *GREEN)
    e += rect(600, 270, 160, 50, "Subagent N", *GREEN)
    for y in [155, 225, 295]:
        e += arrow(400, 200, 595, y, stroke="#2e7d32")
    e += arrow(680, 130, 680, 90, stroke="#9e9e9e")
    e += arrow(680, 90, 300, 90, stroke="#9e9e9e")
    e += arrow(300, 90, 300, 170, stroke="#9e9e9e", label="summary (XML)")

    e += rect(850, 170, 280, 60, "AgentRunBatch scheduler\n3-stage: 5 now → 700ms → maxConcurrency",
              *YELLOW)

    # --- Goal (serial autonomous) ---
    e += [text(60, 380, "②  Goal mode  (serial autonomous, single agent)", size=20, stroke="#ad1457")]
    e += rect(200, 410, 200, 60, "Main agent", *PINK)

    e += rect(500, 410, 90, 60, "active", *GREEN)
    e += rect(620, 410, 90, 60, "paused", *YELLOW)
    e += rect(740, 410, 90, 60, "blocked", *ORANGE)
    e += rect(860, 410, 90, 60, "complete", *GRAY)
    e += arrow(590, 440, 615, 440); e += arrow(710, 440, 735, 440); e += arrow(830, 440, 855, 440)
    e += arrow(665, 440, 590, 440, stroke="#9e9e9e", label="resume")

    e += rect(1000, 410, 220, 60, "continuation driver\nauto-drives next turn", *PURPLE)
    e += arrow(950, 440, 995, 440, label="active →")
    e += arrow(1100, 410, 1100, 360, stroke="#9e9e9e")
    e += arrow(1100, 360, 300, 360, stroke="#9e9e9e")
    e += arrow(300, 360, 300, 410, stroke="#9e9e9e", label="next turn")

    # --- One-off Subagent ---
    e += [text(60, 560, "③  One-off Subagent  (Agent tool, isolated)", size=20, stroke="#6a1b9a")]
    e += rect(200, 590, 200, 60, "Main agent", *PURPLE)
    e += rect(500, 590, 200, 60, "Subagent\n(coder / explore / plan)", *TEAL)
    e += arrow(400, 620, 495, 620, label="spawn")
    e += arrow(600, 590, 600, 540, stroke="#9e9e9e")
    e += arrow(600, 540, 300, 540, stroke="#9e9e9e")
    e += arrow(300, 540, 300, 590, stroke="#9e9e9e", label="summary")
    e += rect(800, 590, 280, 60, "3 profiles · no Agent tool\n(can't spawn sub-sub)", *GRAY)

    save(path, e, "03-multi-agent")


# ---------- Diagram 4: Wire / Op / Model persistence ----------

def diagram_04_wire(path: str) -> None:
    e: list[dict] = []
    e += [text(60, 40, "Wire Protocol · Op/Model Event Sourcing", size=28, bold=True)]

    # left: dispatch flow
    e += [text(60, 110, "dispatch(op) — atomic 4-step", size=18, stroke="#1565c0")]
    e += rect(80,  140, 220, 50, "1. zod schema validate", *BLUE)
    e += rect(80,  210, 220, 50, "2. apply(state, payload) → new state", *BLUE)
    e += rect(80,  280, 220, 50, "3. append to wire.jsonl", *BLUE)
    e += rect(80,  350, 220, 50, "4. publish toEvent → IEventBus", *BLUE)
    for y in [190, 260, 330]:
        e += arrow(190, y, 190, y + 20, stroke="#1565c0")

    # right: Model state
    e += [text(500, 110, "Model state (per-agent, frozen)", size=18, stroke="#ad1457")]
    e += rect(500, 140, 240, 50, "SwarmModel", *PINK)
    e += rect(500, 210, 240, 50, "GoalModel", *PINK)
    e += rect(500, 280, 240, 50, "PlanModel", *PINK)
    e += rect(500, 350, 240, 50, "ContextSizeModel", *PINK)
    e += arrow(300, 235, 495, 165, stroke="#9e9e9e", label="updates")

    # bottom: persistence + restore
    e += [text(60, 440, "Persistence & Restore", size=18, stroke="#6a1b9a")]
    e += rect(80,  470, 220, 70, "~/.kimi-code/.../agents/main/wire.jsonl\n(append-only)", *PURPLE)
    e += rect(380, 470, 220, 70, "fork = copy log\n+ insert forked marker", *PURPLE)
    e += rect(680, 470, 220, 70, "restore = replay apply\n(no events, no writes)", *PURPLE)

    e += arrow(190, 400, 190, 465, stroke="#6a1b9a")
    e += arrow(300, 505, 375, 505, stroke="#6a1b9a")
    e += arrow(600, 505, 675, 505, stroke="#6a1b9a")

    # migration
    e += rect(80, 590, 820, 50, "protocol_version + migration chain (v1.0 → v1.5): old sessions replay on new code",
              *GRAY)

    save(path, e, "04-wire")


# ---------- Diagram 5: Tool call full pipeline ----------

def diagram_05_tools(path: str) -> None:
    e: list[dict] = []
    e += [text(60, 40, "Tool Call Pipeline (resolveExecution → approve → execute)", size=26, bold=True)]

    # LLM calls tool
    e += rect(60, 110, 200, 60, "LLM returns\ntool_call", *BLUE)
    e += arrow(260, 140, 315, 140)

    # resolveExecution
    e += rect(320, 110, 220, 60, "resolveExecution(input)\n→ ToolExecution", *YELLOW)
    e += [text(320, 95, "① declare intent", size=14, stroke="#f57c00")]
    e += arrow(540, 140, 595, 140)

    # permission chain
    e += rect(600, 110, 220, 60, "Permission chain\n(19 policies, first wins)", *PINK)
    e += [text(600, 95, "② decide allow/deny/ask", size=14, stroke="#ad1457")]
    e += arrow(820, 140, 875, 140)

    # three outcomes
    e += rect(880, 60,  160, 50, "allow", *GREEN)
    e += rect(880, 125, 160, 50, "ask user", *ORANGE)
    e += rect(880, 190, 160, 50, "deny", *PINK)

    # execute
    e += arrow(960, 85,  960, 240, stroke="#9e9e9e")
    e += arrow(960, 240, 960, 290, stroke="#9e9e9e", label="if allow")
    e += rect(820, 290, 280, 60, "execute(ctx)\nvia toolScheduler", *TEAL)
    e += [text(820, 275, "③ run (respecting conflict graph)", size=14, stroke="#00695c")]

    # accesses
    e += [text(60, 230, "ToolExecution carries:", size=16, stroke="#1565c0")]
    e += rect(60,  260, 220, 40, "accesses (file read/write)", *BLUE)
    e += rect(60,  310, 220, 40, "approvalRule (with payload)", *BLUE)
    e += rect(60,  360, 220, 40, "display (UI hint)", *BLUE)
    e += rect(60,  410, 220, 40, "execute closure", *BLUE)
    e += arrow(280, 280, 315, 145, stroke="#9e9e9e")
    e += arrow(280, 330, 315, 155, stroke="#9e9e9e")

    # conflict detection
    e += [text(60, 500, "Conflict detection (parallel safety)", size=18, stroke="#6a1b9a")]
    e += rect(60,  530, 220, 50, "Read + Read → ok", *GREEN)
    e += rect(300, 530, 220, 50, "Read + Write → serialise", *ORANGE)
    e += rect(540, 530, 220, 50, "kind:'all' → blocks all", *PINK)

    save(path, e, "05-tools")


# ---------- Diagram 6: Provider / kosong ----------

def diagram_06_providers(path: str) -> None:
    e: list[dict] = []
    e += [text(60, 40, "kosong · LLM Provider Abstraction", size=28, bold=True)]

    # top: unified interface
    e += rect(300, 110, 500, 70, "ChatProvider.generate()\n→ StreamedMessage (async iterator)",
              *BLUE)

    # 5 providers below
    providers = [
        ("OpenAI Chat\n(legacy, /v1/chat/completions)", *YELLOW),
        ("OpenAI Responses\n(/v1/responses, reasoning)", *YELLOW),
        ("Anthropic Messages\n(thinking, tool_use)", *GREEN),
        ("Google GenAI\n(functionCall, thought)", *PINK),
        ("Kimi (KFC)\n+ Ollama (compat)", *PURPLE),
    ]
    for i, (lbl, bg, st) in enumerate(providers):
        x = 60 + i * 230
        e += rect(x, 260, 200, 70, lbl, bg, st)
        e += arrow(x + 100, 260, x + 100, 185, stroke="#9e9e9e")

    # generate loop
    e += [text(60, 380, "generate() — pure function loop", size=18, stroke="#ad1457")]
    e += rect(60,  410, 180, 60, "for await\n(part of stream)", *PINK)
    e += rect(280, 410, 180, 60, "merge same-type parts\n(text+text, tool+tool)", *PINK)
    e += rect(500, 410, 180, 60, "streamIndex Map\n(parallel tool call routing)", *PINK)
    e += rect(720, 410, 220, 60, "onToolCall fires AFTER stream ends\n(prevents half-parsed args)", *PINK)
    e += arrow(240, 440, 275, 440); e += arrow(460, 440, 495, 440); e += arrow(680, 440, 715, 440)

    # normalisation outputs
    e += [text(60, 520, "Unified outputs", size=18, stroke="#00695c")]
    e += rect(60,  550, 200, 50, "FinishReason\n(completed/tool_calls/truncated/...)", *TEAL)
    e += rect(280, 550, 200, 50, "ModelCapability\n(max_context, supports_vision)", *TEAL)
    e += rect(500, 550, 200, 50, "TokenUsage\n(input/output/cache)", *TEAL)
    e += rect(720, 550, 220, 50, "Errors\n(APIProviderRateLimitError, ...)", *TEAL)

    save(path, e, "06-providers")


# ---------- Main ----------

if __name__ == "__main__":
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    diagram_01_overall(f"{base}/01-overall.excalidraw")
    diagram_02_loop(f"{base}/02-loop.excalidraw")
    diagram_03_multi_agent(f"{base}/03-multi-agent.excalidraw")
    diagram_04_wire(f"{base}/04-wire.excalidraw")
    diagram_05_tools(f"{base}/05-tools.excalidraw")
    diagram_06_providers(f"{base}/06-providers.excalidraw")
    print("\nAll diagrams generated. Open any .excalidraw file at https://excalidraw.com")
