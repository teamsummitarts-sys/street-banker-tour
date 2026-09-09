"""Opaque browser-storage namespace, isolated by authenticated Room identity."""
import hashlib
import hmac

from flask import g


def account_scope(app):
    secret = app.secret_key
    if not secret:
        return ''
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    identity = getattr(g, 'song_builder_csrf_account', g.song_builder_account)
    return hmac.new(secret, ('room-browser-storage:' + identity).encode('utf-8'), hashlib.sha256).hexdigest()
