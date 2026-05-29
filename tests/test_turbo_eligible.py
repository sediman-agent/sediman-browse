"""Tests for Enhanced Turbo Mode — _is_turbo_eligible expanded keywords."""
from __future__ import annotations

from unittest.mock import MagicMock

from sediman.agent.loop import AgentLoop


class TestIsTurboEligible:
    def _make_loop(self):
        return AgentLoop(llm_provider=MagicMock(), browser_session=MagicMock(), max_steps=5)

    def test_original_action_verbs(self):
        loop = self._make_loop()
        assert loop._is_turbo_eligible("go to google.com")
        assert loop._is_turbo_eligible("search for cats")
        assert loop._is_turbo_eligible("open amazon")

    def test_new_action_verbs_read(self):
        loop = self._make_loop()
        assert loop._is_turbo_eligible("read the article on example.com")

    def test_new_action_verbs_copy(self):
        loop = self._make_loop()
        assert loop._is_turbo_eligible("copy the text from this page")

    def test_new_action_verbs_login(self):
        loop = self._make_loop()
        assert loop._is_turbo_eligible("login to my account")

    def test_new_action_verbs_submit(self):
        loop = self._make_loop()
        assert loop._is_turbo_eligible("submit the form")

    def test_new_action_verbs_register(self):
        loop = self._make_loop()
        assert loop._is_turbo_eligible("register a new account")

    def test_new_action_verbs_verify(self):
        loop = self._make_loop()
        assert loop._is_turbo_eligible("verify my email address")

    def test_new_action_verbs_test(self):
        loop = self._make_loop()
        assert loop._is_turbo_eligible("test the login flow")

    def test_new_action_verbs_follow(self):
        loop = self._make_loop()
        assert loop._is_turbo_eligible("follow the link to the docs")

    def test_not_eligible_with_conversation(self):
        loop = self._make_loop()
        loop._conversation = [{"role": "user", "content": "hi"}]
        assert not loop._is_turbo_eligible("go to google")

    def test_not_eligible_too_long(self):
        loop = self._make_loop()
        assert not loop._is_turbo_eligible("go to " + "x" * 600)

    def test_not_eligible_schedule_keyword(self):
        loop = self._make_loop()
        assert not loop._is_turbo_eligible("schedule a task every hour")

    def test_not_eligible_chat_keyword(self):
        loop = self._make_loop()
        assert not loop._is_turbo_eligible("what is the meaning of life")

    def test_not_eligible_ambiguous(self):
        loop = self._make_loop()
        assert not loop._is_turbo_eligible("actually go to google")

    def test_not_eligible_no_action_verb(self):
        loop = self._make_loop()
        assert not loop._is_turbo_eligible("tell me about quantum physics")

    def test_not_eligible_schedule_multilang(self):
        loop = self._make_loop()
        assert not loop._is_turbo_eligible("每天检查股票价格")
        assert not loop._is_turbo_eligible("monitor diariamente")
        assert not loop._is_turbo_eligible("check monitor täglich")

    def test_not_eligible_chat_multilang(self):
        loop = self._make_loop()
        assert not loop._is_turbo_eligible("什么是量子物理")
        assert not loop._is_turbo_eligible("explicar la física")

    def test_not_eligible_ambiguous_multilang(self):
        loop = self._make_loop()
        assert not loop._is_turbo_eligible("抱歉 打开百度")
        assert not loop._is_turbo_eligible("espera busca google")

    def test_eligible_multilang_action_verbs(self):
        loop = self._make_loop()
        assert loop._is_turbo_eligible("打开google.com")
        assert loop._is_turbo_eligible("abrir amazon")
        assert loop._is_turbo_eligible("ouvrir le site web")
        assert loop._is_turbo_eligible("öffne google.de")
        assert loop._is_turbo_eligible("検索 cats")
        assert loop._is_turbo_eligible("검색 cats")
        assert loop._is_turbo_eligible("登录我的账号")
        assert loop._is_turbo_eligible("clic aquí")
        assert loop._is_turbo_eligible("скачать файл")
