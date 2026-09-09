"""Auth utilities: password hashing, token generation, email sending."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

import bcrypt

from utils.email import send_email

BASE_URL = os.getenv("SERVICE_URL_CARHERO", "https://carhero.chat")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def send_verification_email(email: str, token: str, name: str = ""):
    verify_url = f"{BASE_URL}/auth/verify/{token}"
    greeting = f"Hi {name}," if name else "Hi,"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F5F5F5;font-family:'Inter',Arial,sans-serif;">
<div style="max-width:500px;margin:0 auto;padding:40px 20px;">
  <div style="background:#fff;border-radius:8px;padding:32px;border:1px solid #E5E7EB;">
    <h1 style="font-size:20px;font-weight:700;color:#1A1A1A;margin:0 0 16px;">
      Welcome to CarHero
    </h1>
    <p style="color:#4B5563;font-size:14px;line-height:1.6;margin:0 0 16px;">
      {greeting}
    </p>
    <p style="color:#4B5563;font-size:14px;line-height:1.6;margin:0 0 24px;">
      Please verify your email address to activate your account.
    </p>
    <a href="{verify_url}"
       style="display:inline-block;background:#000;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600;">
      Verify Email
    </a>
    <p style="color:#9CA3AF;font-size:12px;margin:24px 0 0;">
      If you didn't create an account, you can ignore this email.
    </p>
  </div>
</div>
</body></html>"""

    send_email(
        to=email,
        subject="Verify your CarHero account",
        html_body=html,
        text_body=f"{greeting}\n\nVerify your email: {verify_url}\n\nIf you didn't create an account, ignore this.",
        tag="verify",
    )


def send_invite_email(email: str, token: str, inviter_name: str = "", message: str = ""):
    join_url = f"{BASE_URL}/auth/invite/{token}"
    personal_msg = ""
    if message:
        personal_msg = f"""
    <div style="background:#F9FAFB;border-radius:6px;padding:16px;margin:0 0 20px;border-left:3px solid #1A1A1A;">
      <p style="color:#6B7280;font-size:12px;margin:0 0 4px;font-weight:600;">Personal message from {inviter_name or 'the team'}:</p>
      <p style="color:#374151;font-size:14px;line-height:1.5;margin:0;font-style:italic;">"{message}"</p>
    </div>"""
    invited_by = f" by {inviter_name}" if inviter_name else ""
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F5F5F5;font-family:'Inter',Arial,sans-serif;">
<div style="max-width:500px;margin:0 auto;padding:40px 20px;">
  <div style="background:#fff;border-radius:8px;padding:32px;border:1px solid #E5E7EB;">
    <div style="margin:0 0 24px;">
      <span style="font-family:'DM Serif Display',Georgia,serif;font-size:22px;font-weight:700;color:#1A1A1A;">CarHero</span>
    </div>
    <h1 style="font-size:20px;font-weight:700;color:#1A1A1A;margin:0 0 12px;">
      You're invited to join CarHero
    </h1>
    <p style="color:#4B5563;font-size:14px;line-height:1.6;margin:0 0 16px;">
      You've been invited{invited_by} to join CarHero — the smartest way to find, compare and track premium cars across Europe.
    </p>
    {personal_msg}
    <p style="color:#4B5563;font-size:14px;line-height:1.6;margin:0 0 8px;">
      With CarHero you can:
    </p>
    <ul style="color:#4B5563;font-size:14px;line-height:1.8;margin:0 0 24px;padding-left:20px;">
      <li>Search 40,000+ premium listings across 17 EU countries</li>
      <li>Get AI-powered deal analysis and investment scores</li>
      <li>Track price drops and market trends in real time</li>
    </ul>
    <a href="{join_url}"
       style="display:inline-block;background:#1A1A1A;color:#fff;padding:14px 32px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600;letter-spacing:0.3px;">
      Join CarHero
    </a>
    <p style="color:#9CA3AF;font-size:12px;margin:24px 0 0;">
      If you weren't expecting this, you can safely ignore this email.
    </p>
  </div>
  <p style="text-align:center;color:#9CA3AF;font-size:11px;margin:16px 0 0;">
    CarHero &middot; Premium car marketplace intelligence
  </p>
</div>
</body></html>"""

    send_email(
        to=email,
        subject=f"You're invited to join CarHero",
        html_body=html,
        text_body=(
            f"You've been invited{invited_by} to join CarHero!\n\n"
            f"{('Message: ' + message + chr(10) + chr(10)) if message else ''}"
            f"Join here: {join_url}\n\n"
            f"If you weren't expecting this, you can safely ignore this email."
        ),
        tag="invite",
    )


def send_reset_email(email: str, token: str):
    reset_url = f"{BASE_URL}/auth/reset/{token}"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F5F5F5;font-family:'Inter',Arial,sans-serif;">
<div style="max-width:500px;margin:0 auto;padding:40px 20px;">
  <div style="background:#fff;border-radius:8px;padding:32px;border:1px solid #E5E7EB;">
    <h1 style="font-size:20px;font-weight:700;color:#1A1A1A;margin:0 0 16px;">
      Reset your password
    </h1>
    <p style="color:#4B5563;font-size:14px;line-height:1.6;margin:0 0 24px;">
      Click the button below to set a new password. This link expires in 1 hour.
    </p>
    <a href="{reset_url}"
       style="display:inline-block;background:#000;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600;">
      Reset Password
    </a>
    <p style="color:#9CA3AF;font-size:12px;margin:24px 0 0;">
      If you didn't request this, you can safely ignore this email.
    </p>
  </div>
</div>
</body></html>"""

    send_email(
        to=email,
        subject="Reset your CarHero password",
        html_body=html,
        text_body=f"Reset your password: {reset_url}\n\nThis link expires in 1 hour.",
        tag="reset",
    )
