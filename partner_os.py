"""Partner OS - the guard.

The main app authorises by hand: `user = current_user()` then
`if user is None: return login_required_redirect()`, copied into roughly a
hundred and twenty handlers, with row ownership left to whether the handler
remembered to pass `user["id"]` into the store call. That works until it
does not, and this repo has shipped that failure twice.

Partner routes do not get to repeat it. `@require("permission")` is the
boundary: it resolves the tenant, refuses a request with no seat, refuses a
seat without the permission, and hands the handler its partner and member
as the first two arguments so there is no way to write a partner route that
forgot to scope itself.

A template hiding a button is cosmetic. This is the check.
"""
from functools import wraps

from flask import Blueprint, abort, g, redirect, render_template, request, session, url_for

import db as store
import partner_store as pstore

bp = Blueprint("partner", __name__, url_prefix="/partner")


def _me():
    uid = session.get("user_id")
    return store.get_user(uid) if uid else None


def current_partner():
    """The tenant this request resolved to, or None for Street Banker."""
    return getattr(g, "partner", None)


def current_member():
    return getattr(g, "partner_member", None)


def require(permission="view"):
    """Server-side check before every partner handler.

    Order is deliberate. Not signed in is a redirect, because it is
    recoverable. Signed in with no seat is a 404, not a 403: a stranger
    should not be able to learn that a partner exists at this address by
    the shape of the refusal. A seat without the permission is a 403,
    because at that point they already know the tenant exists.
    """
    def wrap(fn):
        @wraps(fn)
        def guarded(*args, **kwargs):
            user = _me()
            if user is None:
                return redirect(url_for("login", next=request.path))
            partner = current_partner()
            if partner is None:
                abort(404)
            member = current_member()
            if member is None:
                member = pstore.get_member(partner["id"], user_id=user["id"],
                                           email=user.get("email"))
            if member is None:
                abort(404)
            if not pstore.can(member, permission):
                abort(403)
            pstore.touch_member(member["id"])
            return fn(partner, member, *args, **kwargs)
        return guarded
    return wrap


def owned_user_or_404(partner, user_id):
    """Every route that names an artist by id goes through here.

    Ownership is asked of the database, not inferred from the fact that the
    id arrived in a URL the partner was allowed to load.
    """
    if not pstore.owns_user(partner["id"], user_id):
        abort(404)
    user = store.get_user(user_id)
    if user is None:
        abort(404)
    return user


@bp.route("/")
@require("view")
def home(partner, member):
    roster = pstore.roster(partner["id"])
    return render_template("partner/home.html",
                           partner=partner, member=member, roster=roster,
                           can=lambda p: pstore.can(member, p),
                           role_label=pstore.ROLE_LABELS.get(member["role"], member["role"]))


@bp.route("/roster")
@require("roster_view")
def roster(partner, member):
    return render_template("partner/roster.html",
                           partner=partner, member=member,
                           roster=pstore.roster(partner["id"]),
                           can=lambda p: pstore.can(member, p),
                           role_label=pstore.ROLE_LABELS.get(member["role"], member["role"]))


@bp.route("/audit")
@require("view")
def audit(partner, member):
    return render_template("partner/audit.html",
                           partner=partner, member=member,
                           trail=pstore.audit_trail(partner["id"]),
                           can=lambda p: pstore.can(member, p),
                           role_label=pstore.ROLE_LABELS.get(member["role"], member["role"]))


def init(app):
    app.register_blueprint(bp)
