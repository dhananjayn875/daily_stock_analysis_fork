# -*- coding: utf-8 -*-
"""
===================================
Multi-Timeframe Chart Vision Analyzer (ICT / SMC)
===================================

Provides multimodal vision analysis on 1D, 4H, and 1H chart screenshots
for technical price action, institutional order blocks, FVG mitigation,
and strict ₹1L portfolio risk management.
"""

from __future__ import annotations

import base64
import logging
import re
import requests
from typing import Any, Dict, List, Optional, Union

from src.config import get_config
from src.services.image_stock_extractor import _resolve_vision_model, _get_api_keys_for_model

logger = logging.getLogger(__name__)

CHART_VISION_SYSTEM_PROMPT = """You are an elite, institutional Price-Action Quantitative Strategy Mentor training a retail student in India managing a strict ₹1 Lakh (₹100,000) capital base.
Your primary objective is to read institutional market footprints (ICT/SMC: Order Blocks, Fair Value Gaps, Liquidity Sweeps, Market Structure Shifts) across the provided multi-timeframe chart images (1D, 4H, 1H) and current market data, and deliver a brutally objective, un-hedged trading execution report.

Output a structured Markdown response with these exact sections:

### 📊 1. Multi-Timeframe Institutional Structure
- **1D (Daily Macro Bias)**: State the macro trend (Institutional Accumulation, Expansion, Retracement, or Distribution) and identify the dominant Order Block (OB).
- **4H (Intermediate Structure)**: State whether there is a recent Break of Structure (BOS), Market Structure Shift (MSS), or unmitigated Fair Value Gap (FVG).
- **1H (Entry & Liquidity)**: Note any stop-hunting liquidity sweeps or rejection wicks.

### 🎯 2. Concrete Execution Matrix (₹1L Portfolio / 1% Risk)
- **Trade Decision**: `TAKE TRADE (Long / Short)` OR `NO TRADE (Stay in Cash / Low Probability)`
- **Exact Limit Entry**: ₹X (aligned with OB / FVG mitigation / swing support)
- **Exact Stop-Loss (Invalidation)**: ₹Y (structural invalidation level)
- **Exact Target (Exit)**: ₹Z (opposing liquidity pool, minimum 1:2 Risk:Reward)
- **Position Sizing**:
  - Capital: ₹100,000 | Max Risk: ₹1,000 (1%)
  - Formula: `Shares = ₹1,000 / |Entry - StopLoss|` (State exact share count)
  - Estimated R:R Ratio: (e.g. 1:2.8)

### 💡 3. Mentorship Rationale ("The Why")
- Explain why the Stop-Loss is placed at this exact structural invalidation level.
- Explain the retail trap that institutional smart money is exploiting at this level.

### 💻 4. Algorithmic Rule (Python IF-THEN)
- Provide a clean 3-5 line Python pseudo-rule / logic defining this entry trigger.
"""


def _fetch_image_as_b64(url_or_b64: str) -> Optional[tuple[str, str]]:
    """Convert URL or base64 data to (b64_str, mime_type)."""
    if not url_or_b64:
        return None
    if url_or_b64.startswith("data:"):
        parts = url_or_b64.split(",", 1)
        if len(parts) == 2:
            mime = "image/png"
            match = re.search(r"data:([^;]+);", parts[0])
            if match:
                mime = match.group(1)
            return parts[1], mime
    if url_or_b64.startswith("http://") or url_or_b64.startswith("https://"):
        try:
            resp = requests.get(url_or_b64, timeout=15)
            if resp.status_code == 200:
                mime = resp.headers.get("Content-Type", "image/png").split(";")[0]
                b64 = base64.b64encode(resp.content).decode("utf-8")
                return b64, mime
        except Exception as e:
            logger.warning(f"[ChartVisionAnalyzer] Failed to download image from {url_or_b64}: {e}")
            return None
    return None


class ChartVisionAnalyzer:
    """Multimodal Chart Vision Analyzer."""

    @classmethod
    def analyze_stock_with_charts(
        cls,
        code: str,
        image_sources: Optional[List[Union[str, bytes]]] = None,
        mode: str = "ta",
        report_language: str = "en",
    ) -> str:
        """Run multi-timeframe chart and price action analysis."""
        cfg = get_config()
        stock_code = (code or "").strip().upper()

        # 1. Fetch live market context
        market_context_lines = []
        try:
            from data_provider.base import DataFetcherManager
            fetcher = DataFetcherManager()
            quote = fetcher.get_realtime_quote(stock_code)
            if quote and getattr(quote, "price", None):
                market_context_lines.append(f"- Current Price: ₹{quote.price}")
                market_context_lines.append(f"- Today High: ₹{quote.high} | Low: ₹{quote.low} | Open: ₹{quote.open}")
                market_context_lines.append(f"- Change %: {getattr(quote, 'pct_chg', 'N/A')}%")
                market_context_lines.append(f"- Volume: {getattr(quote, 'volume', 'N/A')}")
        except Exception as e:
            logger.debug(f"[ChartVisionAnalyzer] Realtime quote fetch skipped: {e}")

        market_info_text = "\n".join(market_context_lines) if market_context_lines else "- Live quote: Not available"

        # 2. Prepare user message content
        content_items: List[Dict[str, Any]] = [
            {
                "type": "text",
                "text": f"Ticker: {stock_code}\nMode: {mode.upper()}\nMarket Context:\n{market_info_text}\n\nPlease analyze the provided multi-timeframe charts and deliver the complete institutional SMC execution matrix."
            }
        ]

        # 3. Process image attachments
        if image_sources:
            for img in image_sources[:3]:
                if isinstance(img, bytes):
                    b64 = base64.b64encode(img).decode("utf-8")
                    mime = "image/png"
                    data_url = f"data:{mime};base64,{b64}"
                    content_items.append({"type": "image_url", "image_url": {"url": data_url}})
                elif isinstance(img, str):
                    res = _fetch_image_as_b64(img)
                    if res:
                        b64, mime = res
                        data_url = f"data:{mime};base64,{b64}"
                        content_items.append({"type": "image_url", "image_url": {"url": data_url}})

        # 4. Resolve Model and call API via litellm
        model = _resolve_vision_model()
        if not model:
            raise ValueError("No Vision LLM configured. Please set GEMINI_API_KEY or VISION_MODEL.")

        keys = _get_api_keys_for_model(model, cfg)
        api_key = keys[0] if keys else None

        import litellm
        messages = [
            {"role": "system", "content": CHART_VISION_SYSTEM_PROMPT},
            {"role": "user", "content": content_items},
        ]

        call_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.2,
            "timeout": 60,
        }
        if api_key:
            call_kwargs["api_key"] = api_key

        try:
            response = litellm.completion(**call_kwargs)
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"[ChartVisionAnalyzer] LLM Vision analysis failed: {e}")
            raise e
