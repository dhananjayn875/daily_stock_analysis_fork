# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from bot.commands.analyze import AnalyzeCommand
from bot.models import BotMessage, ChatType
from src.services.image_stock_extractor import _normalize_code
from src.services.chart_vision_analyzer import ChartVisionAnalyzer, _fetch_image_as_b64


class TestChartVisionAnalyzer(unittest.TestCase):

    def test_normalize_code_indian_stocks(self):
        self.assertEqual(_normalize_code("RELIANCE.NS"), "RELIANCE.NS")
        self.assertEqual(_normalize_code("500325.BO"), "500325.BO")
        self.assertEqual(_normalize_code("JIOFIN.NS"), "JIOFIN.NS")
        self.assertEqual(_normalize_code("AAPL"), "AAPL")
        self.assertEqual(_normalize_code("600519"), "600519")

    def test_analyze_command_validation(self):
        cmd = AnalyzeCommand()
        self.assertIsNone(cmd.validate_args(["RELIANCE.NS"]))
        self.assertIsNone(cmd.validate_args(["500325.BO"]))
        self.assertIsNone(cmd.validate_args(["AAPL"]))
        self.assertIsNotNone(cmd.validate_args(["INVALID$$$"]))

    def test_analyze_command_ta_mode_with_images(self):
        cmd = AnalyzeCommand()
        msg = BotMessage(
            platform="discord",
            message_id="123",
            user_id="u1",
            user_name="user",
            chat_id="c1",
            chat_type=ChatType.GROUP,
            content="/analyze RELIANCE.NS ta",
            image_urls=["https://example.com/chart1.png", "https://example.com/chart2.png"],
        )

        with patch("src.services.chart_vision_analyzer.ChartVisionAnalyzer.analyze_stock_with_charts") as mock_vision:
            mock_vision.return_value = "### 📊 1. Multi-Timeframe Structure\nBullish OB Retest"
            resp = cmd.execute(msg, ["RELIANCE.NS", "ta"])
            self.assertTrue(resp.markdown)
            self.assertIn("Multi-Timeframe Structure", resp.text)
            mock_vision.assert_called_once()


if __name__ == "__main__":
    unittest.main()
