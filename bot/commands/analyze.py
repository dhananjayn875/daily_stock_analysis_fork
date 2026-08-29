# -*- coding: utf-8 -*-
"""
===================================
股票分析命令
===================================

分析指定股票，调用 AI 生成分析报告。
"""

import re
import logging
from typing import List, Optional

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis

logger = logging.getLogger(__name__)


class AnalyzeCommand(BotCommand):
    """
    股票分析命令
    
    分析指定股票代码，生成 AI 分析报告并推送。
    
    用法：
        /analyze 600519       - 分析贵州茅台（精简报告）
        /analyze 600519 full  - 分析并生成完整报告
    """
    
    @property
    def name(self) -> str:
        return "analyze"
    
    @property
    def aliases(self) -> List[str]:
        return ["a", "分析", "查"]
    
    @property
    def description(self) -> str:
        return "分析指定股票"
    
    @property
    def usage(self) -> str:
        return "/analyze <股票代码|Ticker> [mode: fa|ta|full|simple]"
    
    def validate_args(self, args: List[str]) -> Optional[str]:
        """验证参数"""
        if not args:
            return "Please provide a stock code / ticker (e.g. RELIANCE.NS, AAPL, 600519)"
        
        code = args[0].upper()

        # 验证股票代码格式
        # A股：6位数字
        # 港股：HK+5位数字
        # 美股：1-5个大写字母
        # 印度股：TICKER.NS 或 TICKER.BO
        is_a_stock = bool(re.match(r'^\d{6}$', code))
        is_hk_stock = bool(re.match(r'^HK\d{5}$', code))
        is_us_stock = bool(re.match(r'^[A-Z]{1,5}(\.[A-Z]{1,2})?$', code))
        is_in_stock = bool(re.match(r'^[A-Z0-9_]{1,15}\.(?:NS|BO)$', code))

        if not (is_a_stock or is_hk_stock or is_us_stock or is_in_stock):
            return f"Invalid stock ticker: {code} (Format: RELIANCE.NS / 500325.BO / AAPL / 600519 / HK00700)"
        
        return None
    
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """执行分析命令"""
        code = resolve_index_stock_code_for_analysis(args[0])
        
        # 模式解析 (fa, ta, full, simple)
        mode = "simple"
        if len(args) > 1:
            raw_mode = args[1].lower()
            if raw_mode in ["ta", "tech", "priceaction", "pa"]:
                mode = "ta"
            elif raw_mode in ["fa", "fund", "full", "完整", "详细"]:
                mode = "full"
            elif raw_mode in ["simple", "精简"]:
                mode = "simple"

        # 如果附带了图片或者显式指定 ta 模式
        image_urls = getattr(message, "image_urls", []) or []
        if image_urls or mode == "ta":
            try:
                from src.services.chart_vision_analyzer import ChartVisionAnalyzer
                logger.info(f"[AnalyzeCommand] Running Chart Vision & SMC Analysis for {code} with {len(image_urls)} images")
                analysis_text = ChartVisionAnalyzer.analyze_stock_with_charts(
                    code=code,
                    image_sources=image_urls,
                    mode=mode,
                    report_language="en",
                )
                return BotResponse.markdown_response(analysis_text)
            except Exception as e:
                logger.warning(f"[AnalyzeCommand] Chart Vision analysis failed, falling back to standard pipeline: {e}")

        # 默认标准分析管道
        report_type = "full" if mode == "full" else "simple"
        logger.info(f"[AnalyzeCommand] 分析股票: {code}, 报告类型: {report_type}")
        
        try:
            from src.services.task_service import get_task_service
            from src.enums import ReportType
            
            service = get_task_service()
            
            # 提交异步分析任务
            result = service.submit_analysis(
                code=code,
                report_type=ReportType.from_str(report_type),
                source_message=message
            )
            
            if result.get("success"):
                task_id = result.get("task_id", "")
                return BotResponse.markdown_response(
                    f"✅ **Analysis Task Submitted**\n\n"
                    f"• Ticker: `{code}`\n"
                    f"• Mode: {mode.upper()}\n"
                    f"• Task ID: `{task_id[:20]}...`\n\n"
                    f"Report will be delivered to Discord upon completion."
                )
            else:
                error = result.get("error", "Unknown error")
                return BotResponse.error_response(f"Failed to submit analysis task: {error}")
                
        except Exception as e:
            logger.error(f"[AnalyzeCommand] Execution failed: {e}")
            return BotResponse.error_response(f"Analysis failed: {str(e)[:100]}")
