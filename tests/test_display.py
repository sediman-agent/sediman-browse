from __future__ import annotations

from unittest.mock import patch


from sediman.display import (
    COLORS,
    SYMBOLS,
    TaskProgress,
    print_error,
    print_success,
    print_result_panel,
    print_badges,
    print_startup_banner,
    format_error_message,
    friendly_error,
    render_skill_detail,
)


class TestSymbolsAndColors:
    def test_colors_have_all_keys(self):
        assert "success" in COLORS
        assert "error" in COLORS
        assert "warning" in COLORS
        assert "info" in COLORS
        assert "muted" in COLORS

    def test_symbols_have_all_keys(self):
        assert "success" in SYMBOLS
        assert "error" in SYMBOLS
        assert "progress" in SYMBOLS
        assert "info" in SYMBOLS
        assert "scheduled" in SYMBOLS
        assert "skill" in SYMBOLS

    def test_colors_are_valid(self):
        valid = {"green", "red", "yellow", "cyan", "dim", "bright_blue", "magenta"}
        for key, val in COLORS.items():
            assert val in valid, f"Unexpected color: {val} for {key}"


class TestTaskProgress:
    def test_defaults(self):
        tp = TaskProgress()
        assert tp.task == ""
        assert tp.phase == "idle"
        assert tp.step == 0
        assert tp.action == ""

    def test_start_sets_fields(self):
        tp = TaskProgress()
        tp.start("my task")
        assert tp.task == "my task"
        assert tp.phase == "starting"

    def test_update_phase(self):
        tp = TaskProgress()
        tp.start("t")
        tp.update(phase="executing")
        assert tp.phase == "executing"

    def test_update_action(self):
        tp = TaskProgress()
        tp.start("t")
        tp.update(action="click button")
        assert tp.action == "click button"

    def test_update_url(self):
        tp = TaskProgress()
        tp.start("t")
        tp.update(url="https://example.com")
        assert tp.url == "https://example.com"

    def test_update_step(self):
        tp = TaskProgress()
        tp.start("t")
        tp.update(step=3)
        assert tp.step == 3

    def test_update_elapsed(self):
        tp = TaskProgress()
        tp.start("t")
        tp.update()
        assert tp.elapsed >= 0

    def test_stop_sets_live_none(self):
        tp = TaskProgress()
        tp.start("t")
        assert tp._live is not None
        tp.stop()
        assert tp._live is None

    def test_stop_idempotent(self):
        tp = TaskProgress()
        tp.stop()
        assert tp._live is None

    def test_render_text_includes_phase(self):
        tp = TaskProgress()
        tp.start("t")
        tp.update(phase="planning")
        text = tp._render_text()
        rendered = text.plain if hasattr(text, "plain") else str(text)
        assert "Planning" in rendered

    def test_render_text_includes_action(self):
        tp = TaskProgress()
        tp.start("t")
        tp.update(action="searching")
        text = tp._render_text()
        rendered = text.plain if hasattr(text, "plain") else str(text)
        assert "searching" in rendered

    def test_render_text_includes_elapsed(self):
        tp = TaskProgress()
        tp.start("t")
        text = tp._render_text()
        rendered = text.plain if hasattr(text, "plain") else str(text)
        assert "s" in rendered

    def test_render_text_truncates_long_action(self):
        tp = TaskProgress()
        tp.start("t")
        tp.update(action="x" * 100)
        text = tp._render_text()
        rendered = text.plain if hasattr(text, "plain") else str(text)
        assert "..." in rendered

    def test_render_text_uses_phase_label(self):
        tp = TaskProgress()
        tp.start("t")
        labels = ["starting", "planning", "executing", "observing", "reflecting", "delegating", "healing"]
        for phase in labels:
            tp.update(phase=phase)
            text = tp._render_text()
            rendered = text.plain if hasattr(text, "plain") else str(text)
            assert text is not None

    def test_render_text_fallback_label(self):
        tp = TaskProgress()
        tp.start("t")
        tp.update(phase="custom")
        text = tp._render_text()
        rendered = text.plain if hasattr(text, "plain") else str(text)
        assert "Custom" in rendered


class TestPrintError:
    def test_print_with_message(self):
        with patch("sediman.display.console.print") as mock_print:
            print_error("Something broke")
            mock_print.assert_called_once()

    def test_print_with_suggestion(self):
        with patch("sediman.display.console.print") as mock_print:
            print_error("Error", "Try again")
            mock_print.assert_called_once()

    def test_print_error_uses_error_color(self):
        with patch("sediman.display.console.print") as mock_print:
            print_error("msg")
            panel_arg = mock_print.call_args[0][0]
            assert hasattr(panel_arg, "border_style")


class TestPrintSuccess:
    def test_print_with_title_and_body(self):
        with patch("sediman.display.console.print") as mock_print:
            print_success("Done", "Completed successfully")
            assert mock_print.call_count == 2

    def test_print_with_elapsed(self):
        with patch("sediman.display.console.print") as mock_print:
            print_success("Done", "Completed", elapsed=5.2)
            assert mock_print.call_count == 2

    def test_print_multi_line_body(self):
        with patch("sediman.display.console.print") as mock_print:
            print_success("Done", "line1\nline2\nline3")
            assert mock_print.call_count == 2


class TestPrintResultPanel:
    def test_success_result(self):
        with patch("sediman.display.console.print") as mock_print:
            print_result_panel("Completed successfully", elapsed=3.5, success=True)
            assert mock_print.call_count == 2

    def test_failure_result(self):
        with patch("sediman.display.console.print") as mock_print:
            print_result_panel("Failed with error", elapsed=10.0, success=False)
            assert mock_print.call_count == 2

    def test_result_without_elapsed(self):
        with patch("sediman.display.console.print") as mock_print:
            print_result_panel("Result", success=True)
            assert mock_print.call_count == 2

    def test_markdown_fallback_on_error(self):
        with patch("rich.markdown.Markdown", side_effect=Exception("fail")):
            with patch("sediman.display.console.print") as mock_print:
                print_result_panel("**bold** text", success=True)
                assert mock_print.call_count == 2


class TestPrintBadges:
    def test_skill_created(self):
        with patch("sediman.display.console.print") as mock_print:
            print_badges(skill_created="my-skill")
            mock_print.assert_called_once()

    def test_scheduled_job(self):
        with patch("sediman.display.console.print") as mock_print:
            print_badges(scheduled_job_id="abc123", schedule_cron="0 * * * *")
            mock_print.assert_called_once()

    def test_both_badges(self):
        with patch("sediman.display.console.print") as mock_print:
            print_badges(
                skill_created="skill-1",
                scheduled_job_id="job-1",
                schedule_cron="*/5 * * * *",
            )
            assert mock_print.call_count == 2

    def test_no_badges(self):
        with patch("sediman.display.console.print") as mock_print:
            print_badges()
            mock_print.assert_not_called()


class TestPrintStartupBanner:
    def test_default_banner(self):
        with patch("sediman.display.console.print") as mock_print:
            print_startup_banner(provider="openai", model=None, headless=False)
            assert mock_print.call_count == 3

    def test_with_model(self):
        with patch("sediman.display.console.print") as mock_print:
            print_startup_banner(provider="ollama", model="qwen3", headless=True)
            assert mock_print.call_count == 3

    def test_custom_mode(self):
        with patch("sediman.display.console.print") as mock_print:
            print_startup_banner(provider="openai", model="gpt-4", headless=False, mode="recording")
            assert mock_print.call_count == 3


class TestFormatErrorMessage:
    def test_returns_error_info(self):
        message, suggestion = format_error_message(Exception("test error"))
        assert isinstance(message, str)
        assert suggestion is None or isinstance(suggestion, str)

    def test_auth_error_suggestion(self):
        from sediman.errors import ErrorInfo
        with patch("sediman.errors.classify_error") as mock_classify:
            mock_classify.return_value = ErrorInfo("AUTH_ERROR", "Invalid key", "Set your API key")
            message, suggestion = format_error_message(Exception("auth error"))
            assert suggestion is not None


class TestFriendlyError:
    def test_prints_error(self):
        with patch("sediman.display.console.print") as mock_print:
            friendly_error(Exception("something failed"))
            mock_print.assert_called_once()


class TestRenderSkillDetail:
    def test_minimal_skill(self):
        skill_data = {
            "name": "test-skill",
            "description": "A test",
            "version": 1,
            "category": "general",
            "steps": ["step 1"],
        }
        panel = render_skill_detail(skill_data)
        assert "test-skill" in panel.title.plain if hasattr(panel.title, "plain") else "test-skill" in str(panel.title)

    def test_with_all_fields(self):
        skill_data = {
            "name": "full",
            "description": "full skill",
            "version": 2,
            "category": "advanced",
            "created_at": "2024-01-01",
            "trust": "verified",
            "author": "tester",
            "variables": ["VAR1"],
            "warnings": ["short description"],
            "steps": ["step a", "step b"],
        }
        panel = render_skill_detail(skill_data)

    def test_without_optional_fields(self):
        skill_data = {
            "name": "minimal",
            "description": "minimal skill",
            "version": 1,
            "category": "general",
            "steps": [],
        }
        panel = render_skill_detail(skill_data)

    def test_custom_title(self):
        skill_data = {
            "name": "test",
            "description": "desc",
            "version": 1,
            "category": "general",
            "steps": [],
        }
        panel = render_skill_detail(skill_data, title="Custom Title")
