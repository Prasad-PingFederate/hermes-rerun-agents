"""
Active Context Pruning (ACP) & Billion-Context Compression Engine
Hierarchical Multi-Generational Context Management (LSM-Tree Over Prose) for AI Coding Agents.
Zero external dependencies (uses Python 3.10 standard library: dataclasses, re, json, time, hashlib).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def estimate_tokens(text: str) -> int:
    """Accurately estimate token count for prose and code (~4 chars per token)."""
    if not text:
        return 0
    # Average across words and punctuation
    return max(1, len(text) // 4)


def prune_dom(raw_html: str, max_tokens: int = 500) -> str:
    """Active Context Pruning for Playwright DOM snapshots.
    
    Strips noise (<style>, <script>, <svg>, comments, redundant styling divs)
    while preserving interactive elements, test IDs, roles, and error containers.
    """
    if not raw_html or not raw_html.strip():
        return ""

    content = raw_html

    # 1. Strip comments
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)

    # 2. Strip <style>, <script>, <svg>, <noscript>
    content = re.sub(r"<(style|script|svg|noscript)[^>]*>.*?</\1>", "", content, flags=re.DOTALL | re.IGNORECASE)

    # 3. Strip verbose CSS class attributes and inline style attributes to save massive token overhead
    content = re.sub(r'\sstyle="[^"]*"', '', content)
    # Simplify classes: keep only functional or state classes (e.g. error, active, disabled, modal, alert)
    def clean_class(match):
        classes = match.group(1).split()
        meaningful = [c for c in classes if any(k in c.lower() for k in ("error", "alert", "modal", "active", "btn", "input", "nav", "header", "form"))]
        if meaningful:
            return f' class="{" ".join(meaningful[:3])}"'
        return ''
    content = re.sub(r'\sclass="([^"]*)"', clean_class, content)

    # 4. Collapse whitespace
    content = re.sub(r"\n\s*\n+", "\n", content)
    content = re.sub(r"[ \t]+", " ", content)

    # 5. Extract high-value semantic nodes if still too large
    if estimate_tokens(content) > max_tokens:
        high_value_nodes = []
        # Find interactive / testable elements
        pattern = re.compile(
            r"(<(button|a|input|select|textarea|form|h[1-6]|p|div|span)[^>]*(data-testid|role|id|name|placeholder|aria-label)[^>]*>.*?</\2>|<(input|img)[^>]*(data-testid|role|id|name|placeholder|aria-label)[^>]*/>)",
            re.DOTALL | re.IGNORECASE,
        )
        for m in pattern.finditer(content):
            snippet = m.group(0).strip()
            if snippet and snippet not in high_value_nodes:
                high_value_nodes.append(snippet)
                if sum(estimate_tokens(s) for s in high_value_nodes) >= max_tokens:
                    break

        if high_value_nodes:
            content = "<!-- ACP: Compacted DOM Tree -->\n" + "\n".join(high_value_nodes)
        else:
            # Fallback to bounded head/tail slice
            max_chars = max_tokens * 4
            content = content[:max_chars] + "\n<!-- [ACP: DOM truncated] -->"

    return content.strip()


def prune_traceback(raw_tb: str, max_tokens: int = 400) -> str:
    """Active Context Pruning for Python and pytest tracebacks.
    
    Collapses internal test runner frames (_pytest, pluggy, unittest/case)
    while preserving workspace code frames and the final exception message.
    """
    if not raw_tb or not raw_tb.strip():
        return ""

    lines = raw_tb.strip().splitlines()
    pruned_lines: List[str] = []
    collapsed_framework_frames = 0

    skip_patterns = (
        "_pytest/",
        "pluggy/",
        "unittest/case.py",
        "site-packages/",
        "lib/python3.",
        "lib\\python3.",
    )

    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if line indicates a File frame
        if line.strip().startswith("File "):
            is_framework = any(p in line for p in skip_patterns)
            if is_framework:
                collapsed_framework_frames += 1
                # Skip the following code line(s) for this frame
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("File ") and not re.match(r"^[A-Z][A-Za-z0-9_]*Error:", lines[i].strip()):
                    i += 1
                continue
            else:
                if collapsed_framework_frames > 0:
                    pruned_lines.append(f"  [... collapsed {collapsed_framework_frames} framework runner frame(s) ...]")
                    collapsed_framework_frames = 0
                pruned_lines.append(line)
        else:
            pruned_lines.append(line)
        i += 1

    if collapsed_framework_frames > 0:
        pruned_lines.append(f"  [... collapsed {collapsed_framework_frames} framework runner frame(s) ...]")

    result = "\n".join(pruned_lines)
    # Ensure final exception lines are always preserved
    if estimate_tokens(result) > max_tokens:
        result = result[: (max_tokens * 2)] + "\n[...]\n" + "\n".join(lines[-6:])
    return result


def prune_logs(logs: List[str], max_tokens: int = 300) -> List[str]:
    """Active Context Pruning for browser and network console logs.
    
    Deduplicates consecutive identical entries, filters successful 200 HTTP noise,
    and isolates high-signal 4xx/5xx errors and uncaught exceptions.
    """
    if not logs:
        return []

    pruned: List[str] = []
    prev_log: Optional[str] = None
    repeat_count = 0

    for raw_l in logs:
        line = raw_l.strip()
        if not line:
            continue

        # Filter normal HTTP 200/204 network polling logs
        if re.search(r"HTTP\s+20[04]|status:\s*20[04]", line, re.IGNORECASE):
            continue

        if line == prev_log:
            repeat_count += 1
        else:
            if prev_log is not None:
                if repeat_count > 1:
                    pruned.append(f"{prev_log} (repeated {repeat_count}x)")
                else:
                    pruned.append(prev_log)
            prev_log = line
            repeat_count = 1

    if prev_log is not None:
        if repeat_count > 1:
            pruned.append(f"{prev_log} (repeated {repeat_count}x)")
        else:
            pruned.append(prev_log)

    # Token budgeting
    budgeted: List[str] = []
    curr_tokens = 0
    for entry in pruned:
        tok = estimate_tokens(entry)
        if curr_tokens + tok > max_tokens:
            budgeted.append(f"[... {len(pruned) - len(budgeted)} additional log lines omitted by ACP ...]")
            break
        budgeted.append(entry)
        curr_tokens += tok

    return budgeted


@dataclass
class ContextBlock:
    """Hierarchical Context Block (Multi-Generational LSM-tree prose block)."""
    block_id: str
    tier: int  # 0: Active, 1: Capture (short-term), 2: Distill (mid-term), 3: Condense (long-term)
    label: str
    summary: str
    raw_content: str
    raw_tokens: int
    compacted_tokens: int
    direct_block_ids: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class BillionContextManager:
    """Manages multi-generational context compression (LSM-tree over prose).
    
    Keeps cumulative active token consumption low across long-running autonomous
    agent sessions while supporting full reversible decompression and search.
    """

    def __init__(
        self,
        max_active_tokens: int = 4000,
        tier_1_capacity: int = 6,
        tier_2_capacity: int = 12,
    ):
        self.max_active_tokens = max_active_tokens
        self.tier_1_capacity = tier_1_capacity
        self.tier_2_capacity = tier_2_capacity

        # Multi-generational tiers
        self.tier_0_active: List[ContextBlock] = []
        self.tier_1_capture: List[ContextBlock] = []
        self.tier_2_distill: List[ContextBlock] = []
        self.tier_3_condense: List[ContextBlock] = []

        # Index for instant addressability and reversible decompression
        self.block_index: Dict[str, ContextBlock] = {}
        self._block_counter = 0

    def _next_block_id(self, tier: int) -> str:
        self._block_counter += 1
        ts = int(time.time() * 1000) % 1000000
        return f"blk_t{tier}_{ts}_{self._block_counter:03d}"

    def ingest(
        self,
        content: str,
        label: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
        auto_compact: bool = True,
    ) -> ContextBlock:
        """Ingests raw context item, prunes it with ACP, and places it in Tier 0.
        
        Triggers tiered LSM compaction when active tokens exceed max_active_tokens.
        """
        raw_text = str(content)
        raw_tok = estimate_tokens(raw_text)

        # Apply domain ACP pruning based on label
        if label in ("dom", "dom_snapshot", "html"):
            pruned_text = prune_dom(raw_text)
        elif label in ("traceback", "error_trace", "tb"):
            pruned_text = prune_traceback(raw_text)
        elif label in ("logs", "console", "network"):
            lines = raw_text.splitlines()
            pruned_text = "\n".join(prune_logs(lines))
        else:
            pruned_text = raw_text

        compacted_tok = estimate_tokens(pruned_text)
        b_id = self._next_block_id(tier=0)

        block = ContextBlock(
            block_id=b_id,
            tier=0,
            label=label,
            summary=pruned_text,
            raw_content=raw_text,
            raw_tokens=raw_tok,
            compacted_tokens=compacted_tok,
            metadata=metadata or {},
        )

        self.tier_0_active.append(block)
        self.block_index[b_id] = block

        if auto_compact:
            self.compact_if_needed()

        return block

    def get_active_tokens(self) -> int:
        """Sum of compacted tokens currently held in Tier 0 active working memory."""
        return sum(b.compacted_tokens for b in self.tier_0_active)

    def compact_if_needed(self) -> None:
        """Check watermarks and compact older blocks into higher LSM generations."""
        # Check Tier 0 -> Tier 1 compaction
        active_tok = self.get_active_tokens()
        if active_tok > self.max_active_tokens and len(self.tier_0_active) > 1:
            # Move oldest Tier 0 blocks to Tier 1
            num_to_compact = max(1, len(self.tier_0_active) // 2)
            blocks_to_compact = self.tier_0_active[:num_to_compact]
            self.tier_0_active = self.tier_0_active[num_to_compact:]

            # Create Tier 1 compressed block
            combined_summary = "\n---\n".join(
                f"[{b.label.upper()} - {b.block_id}]\n{b.summary}" for b in blocks_to_compact
            )
            combined_raw = "\n---\n".join(b.raw_content for b in blocks_to_compact)
            t1_id = self._next_block_id(tier=1)
            t1_block = ContextBlock(
                block_id=t1_id,
                tier=1,
                label=f"compacted_t0_{len(blocks_to_compact)}items",
                summary=combined_summary,
                raw_content=combined_raw,
                raw_tokens=sum(b.raw_tokens for b in blocks_to_compact),
                compacted_tokens=estimate_tokens(combined_summary),
                direct_block_ids=[b.block_id for b in blocks_to_compact],
            )
            self.tier_1_capture.append(t1_block)
            self.block_index[t1_id] = t1_block

        # Check Tier 1 -> Tier 2 compaction
        if len(self.tier_1_capture) > self.tier_1_capacity:
            num_t1 = len(self.tier_1_capture) // 2
            t1_batch = self.tier_1_capture[:num_t1]
            self.tier_1_capture = self.tier_1_capture[num_t1:]

            # Distill Tier 1 blocks into a high-level milestone summary
            distilled_summary = f"[TIER 2 DISTILLATION - {len(t1_batch)} milestones compact]\n" + "\n".join(
                f"- Block {b.block_id} ({b.label}): {b.summary[:150]}..." for b in t1_batch
            )
            t2_id = self._next_block_id(tier=2)
            t2_block = ContextBlock(
                block_id=t2_id,
                tier=2,
                label="distilled_milestones",
                summary=distilled_summary,
                raw_content="\n===\n".join(b.raw_content for b in t1_batch),
                raw_tokens=sum(b.raw_tokens for b in t1_batch),
                compacted_tokens=estimate_tokens(distilled_summary),
                direct_block_ids=[b.block_id for b in t1_batch],
            )
            self.tier_2_distill.append(t2_block)
            self.block_index[t2_id] = t2_block

        # Check Tier 2 -> Tier 3 condensation
        if len(self.tier_2_distill) > self.tier_2_capacity:
            num_t2 = len(self.tier_2_distill) // 2
            t2_batch = self.tier_2_distill[:num_t2]
            self.tier_2_distill = self.tier_2_distill[num_t2:]

            condensed_summary = f"[TIER 3 LONG-TERM ARCHITECTURE & RECOVERY CONTEXT - {len(t2_batch)} batch]\n" + "\n".join(
                f"* {b.label}: {b.summary[:100]}..." for b in t2_batch
            )
            t3_id = self._next_block_id(tier=3)
            t3_block = ContextBlock(
                block_id=t3_id,
                tier=3,
                label="condensed_architecture_memory",
                summary=condensed_summary,
                raw_content="\n###\n".join(b.raw_content for b in t2_batch),
                raw_tokens=sum(b.raw_tokens for b in t2_batch),
                compacted_tokens=estimate_tokens(condensed_summary),
                direct_block_ids=[b.block_id for b in t2_batch],
            )
            self.tier_3_condense.append(t3_block)
            self.block_index[t3_id] = t3_block

    def decompress(self, block_id: str) -> str:
        """Reversibly retrieve the unabridged raw content of any historical block."""
        block = self.block_index.get(block_id)
        if not block:
            raise KeyError(f"ContextBlock not found: {block_id}")
        return block.raw_content

    def search_context(self, query: str, tier: Optional[int] = None) -> List[Dict[str, Any]]:
        """Query historical compressed context without re-inflating active prompt memory."""
        q_lower = query.lower()
        results: List[Dict[str, Any]] = []

        all_blocks = list(self.block_index.values())
        if tier is not None:
            all_blocks = [b for b in all_blocks if b.tier == tier]

        for b in all_blocks:
            matches_summary = q_lower in b.summary.lower()
            matches_raw = q_lower in b.raw_content.lower()
            matches_label = q_lower in b.label.lower()

            if matches_summary or matches_raw or matches_label:
                snippet = b.summary if len(b.summary) <= 300 else b.summary[:300] + "..."
                results.append({
                    "block_id": b.block_id,
                    "tier": b.tier,
                    "label": b.label,
                    "snippet": snippet,
                    "compacted_tokens": b.compacted_tokens,
                    "raw_tokens": b.raw_tokens,
                    "timestamp": b.timestamp,
                })

        return results

    def acp_status(self) -> Dict[str, Any]:
        """Provides full telemetry on memory health, token consumption, and savings ratio."""
        all_blocks = list(self.block_index.values())
        total_raw_tokens = sum(b.raw_tokens for b in all_blocks)
        total_compacted_tokens = (
            sum(b.compacted_tokens for b in self.tier_0_active)
            + sum(b.compacted_tokens for b in self.tier_1_capture)
            + sum(b.compacted_tokens for b in self.tier_2_distill)
            + sum(b.compacted_tokens for b in self.tier_3_condense)
        )

        tokens_saved = max(0, total_raw_tokens - total_compacted_tokens)
        compression_ratio = (
            round(float(total_raw_tokens) / float(total_compacted_tokens), 2)
            if total_compacted_tokens > 0
            else 1.0
        )

        return {
            "total_blocks": len(all_blocks),
            "tier_0_active_blocks": len(self.tier_0_active),
            "tier_1_capture_blocks": len(self.tier_1_capture),
            "tier_2_distill_blocks": len(self.tier_2_distill),
            "tier_3_condense_blocks": len(self.tier_3_condense),
            "active_tokens": self.get_active_tokens(),
            "total_raw_tokens": total_raw_tokens,
            "total_compacted_tokens": total_compacted_tokens,
            "tokens_saved": tokens_saved,
            "compression_ratio": compression_ratio,
        }

    def build_active_prompt_context(self, max_tokens: int = 2000) -> str:
        """Assembles a high-signal, token-budgeted prompt context across tiers."""
        parts: List[str] = []
        budget = max_tokens

        # 1. Condense / Distill context (Tier 3 / Tier 2) brief anchors
        anchors = []
        for b in self.tier_3_condense + self.tier_2_distill:
            anchors.append(f"[{b.label}]: {b.summary[:120]}...")
        if anchors:
            anchor_text = "### Historical Milestones & Domain Memory:\n" + "\n".join(anchors[:4])
            tok = estimate_tokens(anchor_text)
            if tok < budget // 3:
                parts.append(anchor_text)
                budget -= tok

        # 2. Tier 0 Active working context (newest items prioritized)
        active_items = []
        for b in reversed(self.tier_0_active):
            tok = b.compacted_tokens
            if tok <= budget:
                active_items.insert(0, f"### Context [{b.label.upper()} ({b.block_id})]:\n{b.summary}")
                budget -= tok
            else:
                break

        parts.extend(active_items)
        return "\n\n".join(parts)

