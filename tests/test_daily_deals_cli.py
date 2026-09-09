"""Tests for scripts/daily_deals.py -- CLI entry point."""

import os
import subprocess
import sys

import pytest


class TestDryRun:
    def test_dry_run_outputs_html(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.daily_deals", "--dry-run"],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        assert result.returncode == 0
        assert "<!DOCTYPE html>" in result.stdout
        assert "CarHero" in result.stdout
        assert "Top Price Deals" in result.stdout

    def test_dry_run_has_subject_log(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.daily_deals", "--dry-run"],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        assert "Dry run complete" in result.stderr

    def test_dry_run_with_limits(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.daily_deals", "--dry-run",
             "--deals", "3", "--cheapest", "2"],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        assert result.returncode == 0
        assert "<!DOCTYPE html>" in result.stdout


class TestIntegrationSend:
    """Send a real test email. Only runs with --run-integration."""

    @pytest.mark.skipif(
        not os.getenv("POSTMARK_API_TOKEN"),
        reason="POSTMARK_API_TOKEN not set",
    )
    def test_send_to_test_email(self, request):
        if not request.config.getoption("--run-integration", default=False):
            pytest.skip("pass --run-integration to run")

        to = os.getenv("TO_EMAIL_TEST", "julian@predictivelabs.co.uk")
        result = subprocess.run(
            [sys.executable, "-m", "scripts.daily_deals", "--to", to],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        assert result.returncode == 0
        assert "Sent!" in result.stderr


