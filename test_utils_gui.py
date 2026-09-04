import asyncio
import io
import os
import unittest
from unittest.mock import patch

import bot_discord

from PIL import Image

import utils_gui


class TestFindAccountDots(unittest.TestCase):
    def test_account_layout_uses_seven_rows_per_page(self):
        region = (105, 90, 692, 148)

        with patch.object(utils_gui, "_detect_account_row_centers", return_value=[12, 33, 54, 75, 96, 117]):
            first_row_offset, row_height, visible_rows = utils_gui.get_account_layout(region)

        self.assertEqual(first_row_offset, 12)
        self.assertEqual(row_height, 21)
        self.assertEqual(visible_rows, 7)

    def test_find_account_dots_falls_back_to_full_window_search(self):
        fake_win = type(
            "FakeWin",
            (),
            {"left": 100, "top": 50, "width": 1200, "height": 700, "_hWnd": 123, "isMinimized": False},
        )()

        def fake_locate(path, region=None, confidence=None, grayscale=None):
            if region == (100, 50, 520, 240):
                return (200, 300, 80, 40)
            return None

        with patch.object(utils_gui, "get_game_window", return_value=fake_win), \
             patch.object(utils_gui, "focus_game_window", return_value=True), \
             patch.object(utils_gui, "ACCS_DIR", os.path.dirname(__file__)), \
             patch.object(utils_gui.pyautogui, "locateOnScreen", side_effect=fake_locate), \
             patch.object(utils_gui.pyautogui, "moveTo"), \
             patch.object(utils_gui.pyautogui, "scroll"), \
             patch.object(utils_gui.time, "sleep"), \
             patch("os.path.exists", return_value=True):
            x, y = utils_gui.find_account_dots("dung")

        self.assertEqual((x, y), (540, 320))

    def test_account_row_mapping_and_scroll_before_row_click(self):
        self.assertEqual(utils_gui.get_account_row_for_name("001"), 1)
        self.assertEqual(utils_gui.get_account_row_for_name("015"), 15)
        self.assertEqual(utils_gui.get_account_row_for_name("030"), 30)
        self.assertIsNone(utils_gui.get_account_row_for_name("abc"))
        self.assertEqual(utils_gui.get_account_row_for_name("020"), 20)

        fake_win = type(
            "FakeWin",
            (),
            {"left": 100, "top": 50, "width": 1200, "height": 700, "_hWnd": 123, "isMinimized": False},
        )()

        with patch.object(utils_gui, "get_game_window", return_value=fake_win), \
             patch.object(utils_gui, "focus_game_window", return_value=True), \
             patch.object(utils_gui, "scroll_account_list_to_top") as mock_scroll, \
             patch.object(utils_gui, "scroll_to_target_row") as mock_scroll_target, \
             patch.object(utils_gui.pyautogui, "click") as mock_click:
            x, y = utils_gui.find_account_dots("015")

        self.assertEqual((x, y), (540, 50 + 12 + (15 - 1) * 22))
        mock_scroll.assert_called_once()
        mock_scroll_target.assert_called_once_with(15)
        mock_click.assert_not_called()

    def test_scroll_to_target_row_clicks_each_row_in_sequence(self):
        fake_win = type(
            "FakeWin",
            (),
            {"left": 100, "top": 50, "width": 1200, "height": 700, "_hWnd": 123, "isMinimized": False},
        )()

        with patch.object(utils_gui, "get_game_window", return_value=fake_win), \
             patch.object(utils_gui, "focus_game_window", return_value=True), \
             patch.object(utils_gui.pyautogui, "moveTo") as mock_move, \
             patch.object(utils_gui.pyautogui, "click") as mock_click, \
             patch.object(utils_gui.time, "sleep"):
            result = utils_gui.scroll_to_target_row(3)

        self.assertTrue(result)
        self.assertEqual(mock_click.call_count, 3)
        self.assertEqual(mock_move.call_count, 3)
        mock_click.assert_any_call(540, 50 + 12 + (1 - 1) * 22)
        mock_click.assert_any_call(540, 50 + 12 + (2 - 1) * 22)
        mock_click.assert_any_call(540, 50 + 12 + (3 - 1) * 22)

    def test_capture_reuses_existing_target_coordinates_without_recounting(self):
        fake_win = type(
            "FakeWin",
            (),
            {"left": 100, "top": 50, "width": 1200, "height": 700, "_hWnd": 123, "isMinimized": False},
        )()

        with patch.object(utils_gui, "get_game_window", return_value=fake_win), \
             patch.object(utils_gui, "focus_game_window", return_value=True), \
             patch.object(utils_gui, "scroll_account_list_to_top") as mock_scroll_top, \
             patch.object(utils_gui, "scroll_to_target_row") as mock_scroll_target, \
             patch.object(utils_gui.pyautogui, "screenshot", return_value=Image.new("RGB", (100, 50))) as mock_screenshot:
            result = utils_gui.capture_account_row_image("008", x_coord=540, y_coord=50 + 12 + (8 - 1) * 22)

        self.assertIsInstance(result, io.BytesIO)
        mock_scroll_top.assert_not_called()
        mock_scroll_target.assert_not_called()
        mock_screenshot.assert_called_once()

    def test_capture_uses_same_row_coordinates_once(self):
        fake_win = type(
            "FakeWin",
            (),
            {"left": 100, "top": 50, "width": 1200, "height": 700, "_hWnd": 123, "isMinimized": False},
        )()

        with patch.object(utils_gui, "get_game_window", return_value=fake_win), \
             patch.object(utils_gui, "focus_game_window", return_value=True), \
             patch.object(utils_gui, "scroll_account_list_to_top") as mock_scroll, \
             patch.object(utils_gui, "find_account_dots", return_value=(600, 50 + 14 + (8 - 1) * 22)) as mock_find, \
             patch.object(utils_gui.pyautogui, "screenshot", return_value=Image.new("RGB", (100, 50))) as mock_screenshot:
            result = utils_gui.capture_account_row_image("008")

        self.assertIsInstance(result, io.BytesIO)
        self.assertEqual(mock_find.call_count, 1)
        self.assertEqual(mock_scroll.call_count, 1)
        mock_screenshot.assert_called_once()

    def test_check_focuses_inside_first_account_row_before_down_keys(self):
        fake_win = type(
            "FakeWin",
            (),
            {"left": 100, "top": 50, "width": 1200, "height": 700, "_hWnd": 123, "isMinimized": False},
        )()

        with patch.object(utils_gui, "get_game_window", return_value=fake_win), \
             patch.object(utils_gui, "focus_game_window", return_value=True), \
             patch.object(utils_gui, "scroll_account_list_to_top", return_value=True), \
             patch.object(utils_gui, "_detect_account_row_centers", return_value=[]), \
             patch.object(utils_gui.pyautogui, "moveTo") as mock_move, \
             patch.object(utils_gui.pyautogui, "click") as mock_click, \
             patch.object(utils_gui.pyautogui, "press") as mock_press, \
             patch.object(utils_gui.time, "sleep"):
            utils_gui.find_account_dots_for_check("003")

        focus_point = (100 + 5 + 692 // 2, 50 + 40 + 12)
        mock_move.assert_called_once_with(*focus_point)
        mock_click.assert_called_once_with(*focus_point)
        self.assertEqual(mock_press.call_args_list[0].args, ("home",))
        self.assertEqual(mock_press.call_args_list[1].args, ("down",))
        self.assertEqual(mock_press.call_count, 3)

    def test_check_account_nine_uses_eight_down_keys(self):
        fake_win = type(
            "FakeWin",
            (),
            {"left": 100, "top": 50, "width": 1200, "height": 700, "_hWnd": 123, "isMinimized": False},
        )()

        with patch.object(utils_gui, "get_game_window", return_value=fake_win), \
             patch.object(utils_gui, "focus_game_window", return_value=True), \
             patch.object(utils_gui, "scroll_account_list_to_top", return_value=True), \
             patch.object(utils_gui, "_detect_account_row_centers", return_value=[]), \
             patch.object(utils_gui.pyautogui, "moveTo"), \
             patch.object(utils_gui.pyautogui, "click"), \
             patch.object(utils_gui.pyautogui, "press") as mock_press, \
             patch.object(utils_gui.time, "sleep"):
            utils_gui.find_account_dots_for_check("009")

        self.assertEqual(mock_press.call_args_list[0].args, ("home",))
        self.assertEqual([call.args for call in mock_press.call_args_list[1:]], [("down",)] * 8)

    def test_check_account_one_does_not_press_down(self):
        fake_win = type(
            "FakeWin",
            (),
            {"left": 100, "top": 50, "width": 1200, "height": 700, "_hWnd": 123, "isMinimized": False},
        )()

        with patch.object(utils_gui, "get_game_window", return_value=fake_win), \
             patch.object(utils_gui, "focus_game_window", return_value=True), \
             patch.object(utils_gui, "scroll_account_list_to_top", return_value=True), \
             patch.object(utils_gui, "_detect_account_row_centers", return_value=[]), \
             patch.object(utils_gui.pyautogui, "moveTo"), \
             patch.object(utils_gui.pyautogui, "click"), \
             patch.object(utils_gui.pyautogui, "press") as mock_press, \
             patch.object(utils_gui.time, "sleep"):
            utils_gui.find_account_dots_for_check("001")

        self.assertEqual([call.args for call in mock_press.call_args_list], [("home",)])

    def test_action_on_focuses_game_before_clicking_account(self):
        with patch.object(utils_gui, "focus_game_window", return_value=True) as mock_focus, \
             patch.object(utils_gui, "find_account_dots_for_check", return_value=(600, 100)), \
             patch.object(utils_gui.pyautogui, "moveTo"), \
             patch.object(utils_gui.pyautogui, "click"), \
             patch.object(utils_gui.time, "sleep"):
            result = utils_gui.do_action_on("001")

        self.assertTrue(result[0])
        mock_focus.assert_called_once_with()

    def test_fallback_scroll_uses_game_window_scroll_helper(self):
        fake_win = type(
            "FakeWin",
            (),
            {"left": 100, "top": 50, "width": 1200, "height": 700, "_hWnd": 123, "isMinimized": False},
        )()

        with patch.object(utils_gui, "get_game_window", return_value=fake_win), \
             patch.object(utils_gui, "focus_game_window", return_value=True), \
             patch.object(utils_gui, "scroll_game_window") as mock_scroll_game, \
             patch.object(utils_gui, "ACCS_DIR", os.path.dirname(__file__)), \
             patch.object(utils_gui.pyautogui, "locateOnScreen", return_value=None), \
             patch.object(utils_gui.pyautogui, "moveTo"), \
             patch.object(utils_gui.pyautogui, "scroll") as mock_raw_scroll, \
             patch.object(utils_gui.time, "sleep"), \
             patch("os.path.exists", return_value=True):
            result = utils_gui.find_account_dots("dung")

        self.assertEqual(result, (None, None))
        self.assertGreaterEqual(mock_scroll_game.call_count, 1)
        mock_raw_scroll.assert_not_called()


class TestDiscordCheckMessage(unittest.TestCase):
    def test_send_check_attachment_includes_account_name(self):
        class DummyInteraction:
            def __init__(self):
                self.sent = None

            async def followup_send(self, content=None, file=None, ephemeral=None):
                self.sent = {"content": content, "file": file, "ephemeral": ephemeral}

        interaction = DummyInteraction()
        result = io.BytesIO(b"abc")

        async def run_case():
            await bot_discord._send_check_attachment(interaction, result, "row_001.png", "001")

        asyncio.run(run_case())

        self.assertIn("001", interaction.sent["content"])
        self.assertIsNotNone(interaction.sent["file"])


if __name__ == "__main__":
    unittest.main()
