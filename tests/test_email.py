"""Tests for utils/email.py -- Postmark email sending."""

import os
import json
from unittest.mock import patch, MagicMock

import pytest

from utils.email import send_email


class TestSendEmailUnit:
    """Unit tests that mock the Postmark API."""

    @patch("utils.email.requests.post")
    def test_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ErrorCode": 0, "MessageID": "test-123"},
        )
        result = send_email(
            to="test@example.com",
            subject="Test",
            html_body="<p>Hello</p>",
            api_token="fake-token",
        )
        assert result["ErrorCode"] == 0
        assert result["MessageID"] == "test-123"
        mock_post.assert_called_once()

    @patch("utils.email.requests.post")
    def test_payload_structure(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ErrorCode": 0, "MessageID": "x"},
        )
        send_email(
            to="test@example.com",
            subject="Subject Line",
            html_body="<b>body</b>",
            text_body="body",
            from_email="sender@test.com",
            tag="test-tag",
            api_token="fake-token",
        )
        call_args = mock_post.call_args
        payload = json.loads(call_args.kwargs.get("data") or call_args[1].get("data"))
        assert payload["To"] == "test@example.com"
        assert payload["Subject"] == "Subject Line"
        assert payload["HtmlBody"] == "<b>body</b>"
        assert payload["TextBody"] == "body"
        assert payload["Tag"] == "test-tag"
        assert payload["MessageStream"] == "outbound"

    @patch("utils.email.requests.post")
    def test_from_name_wrapping(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ErrorCode": 0, "MessageID": "x"},
        )
        with patch.dict(os.environ, {"FROM_NAME": "CarHero"}):
            send_email(
                to="test@example.com",
                subject="Test",
                html_body="<p>Hi</p>",
                from_email="info@carhero.chat",
                api_token="fake-token",
            )
        call_args = mock_post.call_args
        payload = json.loads(call_args.kwargs.get("data") or call_args[1].get("data"))
        assert payload["From"] == "CarHero <info@carhero.chat>"

    def test_missing_token(self):
        with patch.dict(os.environ, {}, clear=False):
            result = send_email(
                to="test@example.com",
                subject="Test",
                html_body="<p>Hi</p>",
                api_token=None,
            )
        if not os.getenv("POSTMARK_API_TOKEN"):
            assert "error" in result

    @patch("utils.email.requests.post")
    def test_postmark_error(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=422,
            json=lambda: {"ErrorCode": 300, "Message": "Invalid 'From' address"},
        )
        result = send_email(
            to="test@example.com",
            subject="Test",
            html_body="<p>Hi</p>",
            api_token="fake-token",
        )
        assert result["ErrorCode"] == 300

    @patch("utils.email.requests.post", side_effect=ConnectionError("timeout"))
    def test_network_error(self, mock_post):
        result = send_email(
            to="test@example.com",
            subject="Test",
            html_body="<p>Hi</p>",
            api_token="fake-token",
        )
        assert "error" in result


class TestSendEmailIntegration:
    """Integration test that sends a real email via Postmark.

    Only runs when POSTMARK_API_TOKEN is set and --run-integration is passed.
    Uses TO_EMAIL_TEST from .env.
    """

    @pytest.fixture
    def test_recipient(self):
        return os.getenv("TO_EMAIL_TEST", "julian@predictivelabs.co.uk")

    @pytest.mark.skipif(
        not os.getenv("POSTMARK_API_TOKEN"),
        reason="POSTMARK_API_TOKEN not set",
    )
    def test_send_real_email(self, request, test_recipient):
        if not request.config.getoption("--run-integration", default=False):
            pytest.skip("pass --run-integration to run")

        result = send_email(
            to=test_recipient,
            subject="CarHero Test Email",
            html_body="<p>This is a test email from the CarHero test suite.</p>",
            text_body="This is a test email from the CarHero test suite.",
            from_email="info@carhero.chat",
            tag="test",
        )
        assert result.get("ErrorCode") == 0
        assert "MessageID" in result


