from __future__ import annotations


def get_user_email(sess) -> str | None:
    return sess.get("chat_email")


def set_user_email(sess, email: str):
    sess["chat_email"] = email


def get_user_id(sess) -> int | None:
    return sess.get("chat_uid")


def set_user_id(sess, uid: int):
    sess["chat_uid"] = uid


def clear_user(sess):
    sess.pop("chat_email", None)
    sess.pop("chat_uid", None)
