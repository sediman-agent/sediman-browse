"""Tests for multi-language regex planner and keyword detection."""
from __future__ import annotations

import pytest

from sediman.agent.planner import TaskPlanner
from sediman.agent.locales import (
    SCHEDULE_KEYWORDS,
    CHAT_KEYWORDS,
    AMBIGUOUS_KEYWORDS,
    ACTION_VERBS,
)


# ─── Planner: Chinese ───────────────────────────────────────────────────────

class TestPlannerChinese:
    def test_daily(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("每天检查股票价格")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"
        assert "股票" in plan.browser_task

    def test_hourly(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("每小时检查服务器状态")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 * * * *"

    def test_every_n_minutes(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("每5分钟监控网站")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"

    def test_every_n_hours(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("每2小时检查一次价格")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 */2 * * *"

    def test_weekly(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("每周清理临时文件")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * 1"

    def test_monitor_keyword(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("监控竞争对手网站")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"


# ─── Planner: Traditional Chinese ────────────────────────────────────────────

class TestPlannerTraditionalChinese:
    def test_daily(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("每天檢查股票")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_hourly(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("每小時檢查伺服器")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 * * * *"


# ─── Planner: Spanish ───────────────────────────────────────────────────────

class TestPlannerSpanish:
    def test_every_n_minutes(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("comprobar el precio cada 10 minutos")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/10 * * * *"

    def test_every_n_hours(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("verificar cada 3 horas")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 */3 * * *"

    def test_diariamente(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("enviar reporte diariamente")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_cada_dia(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("comprobar resultados cada día")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_semanalmente(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("limpiar archivos semanalmente")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * 1"


# ─── Planner: French ────────────────────────────────────────────────────────

class TestPlannerFrench:
    def test_chaque_heure(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("vérifier les prix chaque heure")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 * * * *"

    def test_tous_les_jours(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("envoyer le rapport tous les jours")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_every_n_minutes(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("contrôler chaque 15 minutes")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/15 * * * *"

    def test_hebdomadaire(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("rapport hebdomadaire")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * 1"


# ─── Planner: German ────────────────────────────────────────────────────────

class TestPlannerGerman:
    def test_täglich(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("bericht täglich senden")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_stündlich(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("preise stündlich prüfen")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 * * * *"

    def test_alle_n_minuten(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("prüfen alle 10 minuten")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/10 * * * *"

    def test_wöchentlich(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("aufräumen wöchentlich")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * 1"


# ─── Planner: Japanese ──────────────────────────────────────────────────────

class TestPlannerJapanese:
    def test_毎日(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("毎日株価をチェック")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_毎時(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("毎時サーバー確認")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 * * * *"

    def test_毎n分(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("毎5分チェック")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"

    def test_毎週(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("毎週レポート")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * 1"

    def test_モニター(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("ウェブサイトをモニターリング")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"


# ─── Planner: Korean ────────────────────────────────────────────────────────

class TestPlannerKorean:
    def test_매일(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("매일 주가 확인")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_매시간(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("매시간 서버 확인")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 * * * *"

    def test_매n분(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("매 10분 확인")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/10 * * * *"

    def test_매주(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("매주 정리")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * 1"


# ─── Planner: Arabic ────────────────────────────────────────────────────────

class TestPlannerArabic:
    def test_كل_يوم(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("تحقق كل يوم")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_يوميا(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("تحقق يومياً")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"


# ─── Planner: Hindi ─────────────────────────────────────────────────────────

class TestPlannerHindi:
    def test_रोज(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("रोज़ जाँचो")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_हर_n_मिनट(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("हर 10 मिनट जाँचो")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/10 * * * *"


# ─── Planner: Indonesian ────────────────────────────────────────────────────

class TestPlannerIndonesian:
    def test_setiap_hari(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("cek harga setiap hari")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_setiap_n_menit(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("cek setiap 5 menit")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"

    def test_pantau(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("pantau website")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"


# ─── Planner: Russian ───────────────────────────────────────────────────────

class TestPlannerRussian:
    def test_ежедневно(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("проверять ежедневно")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_каждый_час(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("проверять каждый час")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 * * * *"

    def test_мониторинг(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("мониторинг сайта")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"


# ─── Planner: Turkish ───────────────────────────────────────────────────────

class TestPlannerTurkish:
    def test_her_gün(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("her gün kontrol et")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_günlük(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("günlük rapor")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_izle(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("izle web sitesi")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"


# ─── Planner: Portuguese ────────────────────────────────────────────────────

class TestPlannerPortuguese:
    def test_diariamente(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("verificar preços diariamente")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_toda_hora(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("verificar toda hora")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 * * * *"


# ─── Planner: Raw cron ──────────────────────────────────────────────────────

class TestPlannerRawCron:
    def test_standalone_cron(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("*/5 * * * *")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"

    def test_cron_with_label(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("check prices cron: */5 * * * *")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"

    def test_cron_0_star_2(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("0 */2 * * *")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 */2 * * *"

    def test_cron_with_dow(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("0 9 * * 1")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * 1"

    def test_cron_with_time(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("30 14 * * *")
        assert plan.schedule is not None
        assert plan.schedule.cron == "30 14 * * *"


# ─── Planner: Mixed language ────────────────────────────────────────────────

class TestPlannerMixedLanguage:
    def test_chinese_with_english_task(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("每天 check NVIDIA stock price")
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"

    def test_english_still_works(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("get nvidia stock price every 5 minutes")
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"
        assert "nvidia" in plan.browser_task.lower()

    def test_no_schedule_preserves_task(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("打开百度搜索新闻")
        assert plan.schedule is None
        assert plan.browser_task == "打开百度搜索新闻"


# ─── Planner: Strip patterns ────────────────────────────────────────────────

class TestPlannerStripPatterns:
    def test_strip_chinese_schedule(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("检查股票价格 每天")
        assert plan.schedule is not None
        assert "股票" in plan.browser_task

    def test_strip_japanese_schedule(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("株価チェック 毎日")
        assert plan.schedule is not None

    def test_strip_korean_schedule(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("주가 확인 매일")
        assert plan.schedule is not None

    def test_strip_spanish_schedule(self, tmp_sediman_dir):
        planner = TaskPlanner()
        plan = planner.plan("comprobar precios diariamente")
        assert plan.schedule is not None
        assert "precios" in plan.browser_task


# ─── Locales module: keyword coverage ───────────────────────────────────────

class TestLocalesKeywords:
    def test_schedule_keywords_not_empty(self):
        assert len(SCHEDULE_KEYWORDS) > 50

    def test_chat_keywords_not_empty(self):
        assert len(CHAT_KEYWORDS) > 30

    def test_ambiguous_keywords_not_empty(self):
        assert len(AMBIGUOUS_KEYWORDS) > 20

    def test_action_verbs_not_empty(self):
        assert len(ACTION_VERBS) > 100

    def test_schedule_contains_multilang(self):
        joined = " ".join(SCHEDULE_KEYWORDS)
        assert "每天" in joined
        assert "diariamente" in joined or "tous les jours" in joined
        assert "täglich" in joined
        assert "毎日" in joined
        assert "매일" in joined

    def test_action_verbs_contains_multilang(self):
        joined = " ".join(ACTION_VERBS)
        assert "打开" in joined
        assert "abrir" in joined
        assert "ouvrir" in joined
        assert "öffnen" in joined
        assert "開いて" in joined or "開く" in joined
        assert "열기" in joined
