"""SQLite persistence layer.

Real storage for the features that graduated from demo to functional:
user accounts, uploaded royalty statements (+ parsed rows), smart links
(+ click logs), and the submissions inbox. Path is configurable via
DATABASE_PATH so tests and hosted deploys can point elsewhere.

Note for hosting: on ephemeral-disk hosts (e.g. Render free tier) the
file survives requests but not redeploys/restarts — attach a persistent
disk or move to Postgres for durable production data.
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone


def db_path():
    return os.environ.get("DATABASE_PATH") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "instance", "streetbanker.db"
    )


_FALLBACK_WARNED = False


@contextmanager
def get_db():
    path = db_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        # DATABASE_PATH points somewhere we cannot create (e.g. the disk
        # is not mounted yet). Fall back to the local instance dir so the
        # app still boots — degraded (ephemeral) beats down.
        global _FALLBACK_WARNED
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "instance", "streetbanker.db")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not _FALLBACK_WARNED:
            print("WARNING: DATABASE_PATH unusable; falling back to", path)
            _FALLBACK_WARNED = True
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS statements (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                uploaded TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                total REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS statement_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                statement_id TEXT NOT NULL,
                title TEXT,
                source TEXT,
                amount REAL NOT NULL,
                period TEXT
            );
            CREATE TABLE IF NOT EXISTS smart_links (
                slug TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT NOT NULL,
                target TEXT NOT NULL,
                platforms TEXT,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS link_clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                ts TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inbox (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artist_signal_profiles (
                user_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS epk_profiles (
                user_id TEXT PRIMARY KEY,
                data TEXT NOT NULL DEFAULT '{}',
                photo TEXT,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fan_clubs (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                blurb TEXT NOT NULL DEFAULT '',
                price_cents INTEGER NOT NULL DEFAULT 500,
                perks TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 0,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS club_members (
                id TEXT PRIMARY KEY,
                artist_id TEXT NOT NULL,
                member_email TEXT NOT NULL,
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created TEXT NOT NULL,
                UNIQUE(artist_id, member_email)
            );
            CREATE TABLE IF NOT EXISTS club_drops (
                id TEXT PRIMARY KEY,
                artist_id TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                link_url TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_shows (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                venue TEXT NOT NULL,
                city TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'hold',
                notes TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stage_plots (
                user_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            -- rack_presets holds ONE rack per user: the one that loads with
            -- the page. This is the library beside it — many named racks,
            -- so a second setup does not overwrite the first.
            CREATE TABLE IF NOT EXISTS rack_library (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                data TEXT NOT NULL,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rack_lib ON rack_library(user_id, updated);
            CREATE TABLE IF NOT EXISTS rack_presets (
                user_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS light_shows (
                user_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS vault_files (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                path TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'file',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stored_assets (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                path TEXT UNIQUE NOT NULL,
                visibility TEXT NOT NULL DEFAULT 'private'
                    CHECK (visibility IN ('private', 'public')),
                purpose TEXT NOT NULL DEFAULT 'file',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_stored_assets_owner
                ON stored_assets(user_id, visibility);
            CREATE TABLE IF NOT EXISTS epk_shares (
                user_id TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                pin TEXT NOT NULL DEFAULT '',
                expires TEXT NOT NULL DEFAULT '',
                audio TEXT NOT NULL DEFAULT '[]',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS epk_share_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                kind TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                ts TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS onesheet_shares (
                user_id TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                pin TEXT NOT NULL DEFAULT '',
                banner TEXT NOT NULL DEFAULT '',
                audio TEXT NOT NULL DEFAULT '[]',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS onesheet_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                ts TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outreach_items (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                contact TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT '',
                stage TEXT NOT NULL DEFAULT 'saved',
                notes TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS collab_requests (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                genre TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                terms TEXT NOT NULL DEFAULT '',
                ref_url TEXT NOT NULL DEFAULT '',
                closes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS collab_replies (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                message TEXT NOT NULL,
                contact TEXT NOT NULL,
                proposal TEXT NOT NULL DEFAULT '',
                ref_url TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS collab_saves (
                user_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                created TEXT NOT NULL,
                PRIMARY KEY (user_id, request_id)
            );
            CREATE TABLE IF NOT EXISTS tour_board (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                region TEXT NOT NULL DEFAULT '',
                window TEXT NOT NULL DEFAULT '',
                genre TEXT NOT NULL DEFAULT '',
                details TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_board_replies (
                id TEXT PRIMARY KEY,
                listing_id TEXT NOT NULL,
                from_user_id TEXT NOT NULL,
                message TEXT NOT NULL,
                contact TEXT NOT NULL,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS roster_members (
                id TEXT PRIMARY KEY,
                label_id TEXT NOT NULL,
                email TEXT NOT NULL,
                artist_user_id TEXT,
                status TEXT NOT NULL DEFAULT 'invited',
                invite_token TEXT UNIQUE NOT NULL,
                created TEXT NOT NULL,
                UNIQUE(label_id, email)
            );
            CREATE TABLE IF NOT EXISTS sign_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                track_id TEXT NOT NULL,
                doc_key TEXT NOT NULL,
                email TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS beats (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                bpm TEXT NOT NULL DEFAULT '',
                song_key TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            -- The audio itself, plus what the browser measured from it.
            -- One row per beat: re-uploading replaces it rather than
            -- stacking, because a beat is one recording with one BPM.
            -- `peaks` is the pre-computed waveform so the list can draw
            -- 40 beats without decoding 40 files.
            CREATE TABLE IF NOT EXISTS beat_audio (
                beat_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '',
                mime TEXT NOT NULL DEFAULT '',
                bytes INTEGER NOT NULL DEFAULT 0,
                duration REAL,
                peaks TEXT NOT NULL DEFAULT '[]',
                bpm REAL,
                bpm_confidence REAL,
                bpm_alternates TEXT NOT NULL DEFAULT '',
                song_key TEXT NOT NULL DEFAULT '',
                key_fit REAL,
                key_runner_up TEXT NOT NULL DEFAULT '',
                sample_rate REAL,
                created TEXT NOT NULL
            );
            -- A private link to one beat. The unguessable token is the
            -- authorisation; the producer can revoke it or let it lapse.
            CREATE TABLE IF NOT EXISTS beat_shares (
                token TEXT PRIMARY KEY,
                beat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                expires TEXT NOT NULL DEFAULT '',
                plays INTEGER NOT NULL DEFAULT 0,
                last_played TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_beat_shares ON beat_shares(beat_id, revoked);
            CREATE TABLE IF NOT EXISTS beat_licences (
                id TEXT PRIMARY KEY,
                beat_id TEXT NOT NULL,
                producer_id TEXT NOT NULL,
                licensee_name TEXT NOT NULL DEFAULT '',
                licensee_email TEXT NOT NULL DEFAULT '',
                licence_type TEXT NOT NULL DEFAULT 'lease',
                territory TEXT NOT NULL DEFAULT 'Worldwide',
                term TEXT NOT NULL DEFAULT '',
                fee REAL NOT NULL DEFAULT 0,
                producer_split REAL NOT NULL DEFAULT 50,
                terms TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                token TEXT NOT NULL DEFAULT '',
                signed_by TEXT NOT NULL DEFAULT '',
                signed_at TEXT,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS beat_clearances (
                id TEXT PRIMARY KEY,
                beat_id TEXT NOT NULL,
                licence_id TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'channel',
                value TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS beat_uses (
                id TEXT PRIMARY KEY,
                beat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                platform TEXT NOT NULL DEFAULT '',
                found_via TEXT NOT NULL DEFAULT 'manual',
                status TEXT NOT NULL DEFAULT 'open',
                notes TEXT NOT NULL DEFAULT '',
                resolved_amount REAL,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS score_history (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                day TEXT NOT NULL,
                total REAL NOT NULL,
                detail TEXT NOT NULL DEFAULT '{}',
                updated TEXT NOT NULL,
                UNIQUE(user_id, kind, day)
            );
            CREATE TABLE IF NOT EXISTS track_analysis (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                track_id TEXT NOT NULL DEFAULT '',
                filename TEXT NOT NULL DEFAULT '',
                integrated REAL,
                lra REAL,
                true_peak REAL,
                sample_peak REAL,
                short_term_max REAL,
                momentary_max REAL,
                bpm REAL,
                bpm_confidence REAL,
                key TEXT NOT NULL DEFAULT '',
                key_fit REAL,
                duration REAL,
                sample_rate INTEGER,
                channels INTEGER,
                hook_15s REAL,
                hook_30s REAL,
                first_beat REAL,
                bar_seconds REAL,
                grid_confidence REAL,
                engine TEXT NOT NULL DEFAULT '',
                measured_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS os_tracks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                release_title TEXT NOT NULL DEFAULT '',
                release_date TEXT NOT NULL DEFAULT '',
                passport TEXT NOT NULL DEFAULT '{}',
                lockbox TEXT NOT NULL DEFAULT '{}',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ingest_tokens (
                user_id TEXT PRIMARY KEY,
                token TEXT UNIQUE NOT NULL,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS disputes (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                dispute_type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'open',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS team_members (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'manager',
                status TEXT NOT NULL DEFAULT 'invited',
                invite_token TEXT UNIQUE,
                member_user_id TEXT,
                created TEXT NOT NULL,
                joined TEXT,
                UNIQUE(owner_id, email)
            );
            CREATE TABLE IF NOT EXISTS pulse_snapshots (
                user_id TEXT NOT NULL,
                day TEXT NOT NULL,
                followers INTEGER NOT NULL DEFAULT 0,
                popularity INTEGER NOT NULL DEFAULT 0,
                deezer_fans INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day)
            );
            CREATE TABLE IF NOT EXISTS pulse_peers (
                user_id TEXT NOT NULL,
                artist_id TEXT NOT NULL,
                name TEXT NOT NULL,
                image TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                PRIMARY KEY (user_id, artist_id)
            );
            CREATE TABLE IF NOT EXISTS pulse_peer_snapshots (
                user_id TEXT NOT NULL,
                artist_id TEXT NOT NULL,
                day TEXT NOT NULL,
                followers INTEGER NOT NULL DEFAULT 0,
                popularity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, artist_id, day)
            );
            CREATE TABLE IF NOT EXISTS pulse_profiles (
                user_id TEXT PRIMARY KEY,
                artist_id TEXT NOT NULL,
                artist_name TEXT NOT NULL,
                artist_image TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS catalog_tracks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL DEFAULT '',
                album TEXT NOT NULL DEFAULT '',
                art TEXT NOT NULL DEFAULT '',
                preview TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                added TEXT NOT NULL,
                UNIQUE(user_id, title, artist)
            );
            CREATE TABLE IF NOT EXISTS epk_assets (
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                public INTEGER NOT NULL DEFAULT 1,
                updated TEXT NOT NULL,
                PRIMARY KEY (user_id, kind)
            );
            CREATE TABLE IF NOT EXISTS ml_campaigns (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                artist_name TEXT NOT NULL DEFAULT '',
                release_type TEXT NOT NULL DEFAULT 'Single',
                campaign_type TEXT NOT NULL DEFAULT 'release',
                status TEXT NOT NULL DEFAULT 'draft',
                release_date TEXT NOT NULL DEFAULT '',
                cover_url TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                settings TEXT NOT NULL DEFAULT '{}',
                created TEXT NOT NULL,
                updated TEXT NOT NULL,
                published_at TEXT,
                archived_at TEXT
            );
            CREATE TABLE IF NOT EXISTS ml_destinations (
                id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                service_key TEXT NOT NULL,
                service_name TEXT NOT NULL,
                url TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS ml_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                variant_id TEXT,
                event_type TEXT NOT NULL,
                service_key TEXT,
                fan_id TEXT,
                referrer TEXT,
                utm_source TEXT,
                created TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ml_events_campaign
                ON ml_events (campaign_id, event_type);
            CREATE TABLE IF NOT EXISTS ml_fans (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                email TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                first_campaign_id TEXT,
                last_campaign_id TEXT,
                total_visits INTEGER NOT NULL DEFAULT 0,
                total_clicks INTEGER NOT NULL DEFAULT 0,
                total_presaves INTEGER NOT NULL DEFAULT 0,
                total_captures INTEGER NOT NULL DEFAULT 0,
                tags TEXT NOT NULL DEFAULT '[]',
                intent_score INTEGER NOT NULL DEFAULT 0,
                intent_level TEXT NOT NULL DEFAULT 'Cold',
                created TEXT NOT NULL,
                updated TEXT NOT NULL,
                UNIQUE(user_id, email)
            );
            CREATE TABLE IF NOT EXISTS ml_consents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fan_id TEXT NOT NULL,
                campaign_id TEXT,
                consent_type TEXT NOT NULL,
                consent_text TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ml_variants (
                id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                utm_source TEXT NOT NULL DEFAULT '',
                utm_medium TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ro_campaigns (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                ml_campaign_id TEXT,
                title TEXT NOT NULL,
                artist_name TEXT NOT NULL DEFAULT '',
                release_date TEXT NOT NULL DEFAULT '',
                rollout_length INTEGER NOT NULL DEFAULT 14,
                goal TEXT NOT NULL DEFAULT 'presaves',
                platforms TEXT NOT NULL DEFAULT '[]',
                tone TEXT NOT NULL DEFAULT 'premium',
                status TEXT NOT NULL DEFAULT 'draft',
                settings TEXT NOT NULL DEFAULT '{}',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ro_assets (
                id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                file_path TEXT NOT NULL DEFAULT '',
                lyrics_text TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ro_posts (
                id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                variant_id TEXT,
                platform TEXT NOT NULL,
                post_type TEXT NOT NULL DEFAULT 'post',
                phase TEXT NOT NULL,
                caption TEXT NOT NULL DEFAULT '',
                hashtags TEXT NOT NULL DEFAULT '',
                cta TEXT NOT NULL DEFAULT '',
                asset_id TEXT,
                edit_plan TEXT,
                scheduled_date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                published_url TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS street_actions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                priority TEXT NOT NULL DEFAULT 'medium',
                description TEXT NOT NULL DEFAULT '',
                entity_type TEXT NOT NULL DEFAULT '',
                entity_id TEXT NOT NULL DEFAULT '',
                due_date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'new',
                created TEXT NOT NULL,
                updated TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'system',
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                link TEXT NOT NULL DEFAULT '',
                is_read INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                doc_type TEXT NOT NULL DEFAULT 'Agreement',
                note TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recovery_cases (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                estimated_amount REAL NOT NULL DEFAULT 0,
                confidence TEXT NOT NULL DEFAULT 'medium',
                status TEXT NOT NULL DEFAULT 'open',
                deadline TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                evidence_doc_id TEXT,
                payout_result REAL,
                created TEXT NOT NULL,
                updated TEXT NOT NULL,
                closed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS deals (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                deal_type TEXT NOT NULL DEFAULT 'split',
                title TEXT NOT NULL,
                counterparty TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                terms TEXT NOT NULL DEFAULT '',
                doc_id TEXT,
                deadline TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sync_packs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                artist_name TEXT NOT NULL DEFAULT '',
                bpm TEXT NOT NULL DEFAULT '',
                song_key TEXT NOT NULL DEFAULT '',
                moods TEXT NOT NULL DEFAULT '',
                master_status TEXT NOT NULL DEFAULT 'unconfirmed',
                publishing_status TEXT NOT NULL DEFAULT 'unconfirmed',
                ownership_note TEXT NOT NULL DEFAULT '',
                contact_email TEXT NOT NULL DEFAULT '',
                main_url TEXT NOT NULL DEFAULT '',
                instrumental_url TEXT NOT NULL DEFAULT '',
                clean_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                views INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS twin_settings (
                user_id TEXT PRIMARY KEY,
                sources TEXT NOT NULL DEFAULT '[]',
                tone TEXT NOT NULL DEFAULT 'premium',
                do_not_say TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS twin_generations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                output TEXT NOT NULL,
                sources_used TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS revenue_expenses (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                description TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL DEFAULT 0,
                spend_date TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS spotify_presaves (
                id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                spotify_user_id TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                refresh_token_enc TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT NOT NULL DEFAULT '',
                retry_count INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL,
                completed_at TEXT,
                UNIQUE(campaign_id, spotify_user_id)
            );
            CREATE TABLE IF NOT EXISTS api_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hours_rates (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                service TEXT NOT NULL,
                rate REAL NOT NULL DEFAULT 0,
                min_hours REAL NOT NULL DEFAULT 0,
                bookable INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                sort INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL,
                UNIQUE(user_id, service)
            );
            CREATE TABLE IF NOT EXISTS hours_entries (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                day TEXT NOT NULL,
                project TEXT NOT NULL DEFAULT '',
                client TEXT NOT NULL DEFAULT '',
                service TEXT NOT NULL DEFAULT '',
                hours REAL NOT NULL DEFAULT 0,
                rate REAL NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                billed INTEGER NOT NULL DEFAULT 0,
                invoice_id TEXT,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hours_invoices (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                number TEXT NOT NULL,
                client TEXT NOT NULL DEFAULT '',
                project TEXT NOT NULL DEFAULT '',
                hours REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'sent',
                issued TEXT NOT NULL,
                paid TEXT
            );
            CREATE TABLE IF NOT EXISTS hours_bookings (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                service TEXT NOT NULL DEFAULT '',
                who TEXT NOT NULL DEFAULT '',
                contact TEXT NOT NULL DEFAULT '',
                day TEXT NOT NULL,
                start_hour REAL NOT NULL DEFAULT 0,
                hours REAL NOT NULL DEFAULT 1,
                rate REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'requested',
                note TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hours_submissions (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                who TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '',
                day TEXT NOT NULL,
                hours REAL NOT NULL DEFAULT 0,
                rate REAL NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                decided TEXT,
                reason TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hours_blocks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                day TEXT NOT NULL,
                start_hour REAL NOT NULL DEFAULT 9,
                hours REAL NOT NULL DEFAULT 1,
                label TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'work',
                done INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            """
        )
        # Migration: Stripe billing identifiers on users.
        for _col in ("stripe_customer_id", "stripe_subscription_id"):
            try:
                db.execute("ALTER TABLE users ADD COLUMN %s TEXT" % _col)
            except sqlite3.OperationalError:
                pass  # column already exists
        # Migration: hook and beat-grid columns on track_analysis. The
        # table shipped earlier without them, so any database created in
        # between has it already and CREATE TABLE IF NOT EXISTS will not
        # add them. Without this, saving a measurement raises "no such
        # column" on every existing install.
        for _col in ("hook_15s", "hook_30s", "first_beat", "bar_seconds",
                     "grid_confidence"):
            try:
                db.execute("ALTER TABLE track_analysis ADD COLUMN %s REAL"
                           % _col)
            except sqlite3.OperationalError:
                pass  # column already exists

        # Migration: optional territory column on statement rows.
        try:
            db.execute("ALTER TABLE statement_rows ADD COLUMN territory TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: universal-link metadata on smart links.
        try:
            db.execute("ALTER TABLE smart_links ADD COLUMN meta TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: industry identifiers (ISRC/UPC/label) on catalog tracks.
        try:
            db.execute("ALTER TABLE catalog_tracks ADD COLUMN meta TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: public share slug on EPK profiles.
        try:
            db.execute("ALTER TABLE epk_profiles ADD COLUMN slug TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: account plan tiers (fan / artist / pro / label).
        try:
            db.execute("ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'artist'")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: referral engine columns on users.
        for _col in ("ref_code TEXT", "referred_by TEXT",
                     "ref_credited INTEGER NOT NULL DEFAULT 0"):
            try:
                db.execute("ALTER TABLE users ADD COLUMN %s" % _col)
            except sqlite3.OperationalError:
                pass  # column already exists
        # Migration: who an inbox row belongs to. The table shipped
        # without an owner and the page showed every row to every
        # signed-in account: one artist's booking enquiries, pitch
        # emails and lead addresses, readable by all the others.
        try:
            db.execute("ALTER TABLE inbox ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: visit stamps. "What Changed Since Your Last Visit"
        # needs a last visit; it previously had none, which is why the
        # strip was five constants.
        for _col in ("last_seen TEXT", "prev_seen TEXT"):
            try:
                db.execute("ALTER TABLE users ADD COLUMN %s" % _col)
            except sqlite3.OperationalError:
                pass  # column already exists
        # Migration: which recording a document belongs to. Coverage per
        # song was previously read from a hardcoded presence map, so it
        # could never reflect an upload; the vault now needs somewhere to
        # record what the artist told us the file covers.
        try:
            db.execute("ALTER TABLE documents ADD COLUMN track TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: show advancing data on tour shows.
        for _col in ("advance TEXT", "settlement TEXT", "share_token TEXT"):
            try:
                db.execute("ALTER TABLE tour_shows ADD COLUMN %s" % _col)
            except sqlite3.OperationalError:
                pass  # column already exists

        # V2 migration: uploads now carry explicit ownership and visibility.
        # Private business files are backfilled first; intentionally public
        # EPK and campaign artwork then promote the same path when an artist
        # previously selected a Vault image for public use.
        def _backfill(rows, visibility, purpose):
            now = _now()
            for row in rows:
                path = row["path"]
                if not path:
                    continue
                asset_id = uuid.uuid4().hex
                db.execute(
                    "INSERT INTO stored_assets "
                    "(id,user_id,path,visibility,purpose,created,updated) "
                    "VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(path) DO UPDATE SET "
                    "visibility=excluded.visibility,purpose=excluded.purpose,"
                    "updated=excluded.updated "
                    "WHERE stored_assets.user_id=excluded.user_id",
                    (asset_id, row["user_id"], path, visibility, purpose, now, now),
                )

        _backfill(db.execute("SELECT user_id,path FROM documents").fetchall(),
                  "private", "document")
        _backfill(db.execute("SELECT user_id,path FROM vault_files").fetchall(),
                  "private", "vault")
        _backfill(db.execute(
            "SELECT user_id,photo AS path FROM epk_profiles "
            "WHERE photo IS NOT NULL AND photo != ''").fetchall(),
            "public", "epk_photo")
        _backfill(db.execute(
            "SELECT user_id,path FROM epk_assets WHERE public = 1").fetchall(),
            "public", "epk_asset")
        _backfill(db.execute(
            "SELECT user_id,cover_url AS path FROM ml_campaigns "
            "WHERE cover_url LIKE '/uploads/%' OR cover_url LIKE 'r2:%'").fetchall(),
            "public", "campaign_cover")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Stored asset ownership ---------------------------------------------------

def register_stored_asset(user_id, path, visibility="private", purpose="file"):
    """Register an upload without allowing one account to claim another's path."""
    if visibility not in ("private", "public"):
        raise ValueError("visibility must be private or public")
    if not user_id or not path:
        raise ValueError("user_id and path are required")
    asset_id = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO stored_assets "
            "(id,user_id,path,visibility,purpose,created,updated) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET visibility=excluded.visibility,"
            "purpose=excluded.purpose,updated=excluded.updated "
            "WHERE stored_assets.user_id=excluded.user_id",
            (asset_id, user_id, path, visibility, (purpose or "file")[:60], now, now),
        )
        row = db.execute("SELECT * FROM stored_assets WHERE path = ?", (path,)).fetchone()
    if row is None or row["user_id"] != user_id:
        raise ValueError("stored path already belongs to another account")
    return dict(row)


def get_stored_asset(path):
    with get_db() as db:
        row = db.execute("SELECT * FROM stored_assets WHERE path = ?", (path,)).fetchone()
    return dict(row) if row is not None else None


def get_stored_asset_by_id(asset_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM stored_assets WHERE id = ?", (asset_id,)).fetchone()
    return dict(row) if row is not None else None


def set_stored_asset_visibility(user_id, path, visibility):
    if visibility not in ("private", "public"):
        raise ValueError("visibility must be private or public")
    with get_db() as db:
        cur = db.execute(
            "UPDATE stored_assets SET visibility = ?, updated = ? "
            "WHERE user_id = ? AND path = ?",
            (visibility, _now(), user_id, path),
        )
    return cur.rowcount > 0


def delete_stored_asset(user_id, path):
    with get_db() as db:
        cur = db.execute("DELETE FROM stored_assets WHERE user_id = ? AND path = ?",
                         (user_id, path))
    return cur.rowcount > 0


# --- Users -------------------------------------------------------------------

def create_user(email, name, password_hash):
    user_id = uuid.uuid4().hex
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO users (id, email, name, password_hash, created) VALUES (?,?,?,?,?)",
                (user_id, email.lower().strip(), name.strip(), password_hash, _now()),
            )
    except sqlite3.IntegrityError:
        return None
    return user_id


def set_user_plan(user_id, plan):
    with get_db() as db:
        db.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))


def set_stripe_ids(user_id, customer_id, subscription_id):
    with get_db() as db:
        db.execute("UPDATE users SET stripe_customer_id = ?, stripe_subscription_id = ? "
                   "WHERE id = ?", (customer_id, subscription_id, user_id))


def user_by_stripe_customer(customer_id):
    if not customer_id:
        return None
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE stripe_customer_id = ?",
                         (customer_id,)).fetchone()
    return dict(row) if row else None


def set_user_password(user_id, password_hash):
    with get_db() as db:
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                   (password_hash, user_id))


def get_user_by_email(email):
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
    return dict(row) if row else None


def get_user(user_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def roll_seen(user_id):
    """Stamp this visit and return the previous one, or None on a first.

    Two columns rather than one: reading and writing the same stamp
    would make the window close behind you, so the page would say
    "nothing new" the moment it rendered. `prev_seen` is what the
    Overview strip measures from, and it only moves once per session.
    """
    now = _now()
    with get_db() as db:
        row = db.execute("SELECT last_seen FROM users WHERE id = ?",
                         (user_id,)).fetchone()
        if row is None:
            return None
        previous = row["last_seen"]
        db.execute("UPDATE users SET prev_seen = ?, last_seen = ? WHERE id = ?",
                   (previous, now, user_id))
    return previous


def get_prev_seen(user_id):
    with get_db() as db:
        row = db.execute("SELECT prev_seen FROM users WHERE id = ?",
                         (user_id,)).fetchone()
    return row["prev_seen"] if row else None


def activity_since(user_id, since):
    """Counts of things that actually happened, after an ISO timestamp.

    One query per kind, all filtered to this user. Everything here is a
    row with a created/uploaded stamp on it - nothing is inferred, and
    a kind with no rows returns zero rather than being estimated.

    Stamps are second-granular, so the window starts at the second of
    the last visit rather than strictly after it. That can carry one
    second of overlap and show something a second time; the other way
    round drops anything that happened in the same second as the visit,
    and a strip that silently loses events is worse than one that
    occasionally repeats them.
    """
    since = (since or "")[:19]
    out = {}
    with get_db() as db:
        row = db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total), 0) AS amount FROM statements"
            " WHERE user_id = ? AND uploaded >= ?", (user_id, since)).fetchone()
        out["statements"], out["statement_total"] = row["n"], round(row["amount"], 2)
        out["fans"] = db.execute(
            "SELECT COUNT(*) AS n FROM ml_fans WHERE user_id = ? AND created >= ?",
            (user_id, since)).fetchone()["n"]
        for key, event_type in (("visits", "page_view"), ("clicks", "service_click"),
                                ("presaves", "presave_notify")):
            out[key] = db.execute(
                "SELECT COUNT(*) AS n FROM ml_events e JOIN ml_campaigns c"
                " ON c.id = e.campaign_id WHERE c.user_id = ? AND e.event_type = ?"
                " AND e.created >= ?", (user_id, event_type, since)).fetchone()["n"]
        out["notifications"] = db.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND created >= ?",
            (user_id, since)).fetchone()["n"]
        out["cases_opened"] = db.execute(
            "SELECT COUNT(*) AS n FROM recovery_cases WHERE user_id = ? AND created >= ?",
            (user_id, since)).fetchone()["n"]
        row = db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(payout_result), 0) AS amount"
            " FROM recovery_cases WHERE user_id = ? AND status = 'won'"
            " AND updated >= ?", (user_id, since)).fetchone()
        out["cases_won"], out["recovered"] = row["n"], round(row["amount"], 2)
        out["documents"] = db.execute(
            "SELECT COUNT(*) AS n FROM documents WHERE user_id = ? AND created >= ?",
            (user_id, since)).fetchone()["n"]
    return out


def list_users():
    """Id, email and plan only - deliberately not SELECT *.

    Used at boot to put owner accounts on their plan. Password hashes and
    everything else stay where they are; a helper that hands out whole
    user rows is one careless caller away from leaking them into a
    template."""
    with get_db() as db:
        rows = db.execute("SELECT id, email, plan FROM users").fetchall()
    return [dict(r) for r in rows]


# --- Statements --------------------------------------------------------------

def save_statement(user_id, filename, rows):
    statement_id = uuid.uuid4().hex
    total = round(sum(r["amount"] for r in rows), 2)
    with get_db() as db:
        db.execute(
            "INSERT INTO statements (id, user_id, filename, uploaded, row_count, total) VALUES (?,?,?,?,?,?)",
            (statement_id, user_id, filename, _now(), len(rows), total),
        )
        db.executemany(
            "INSERT INTO statement_rows (statement_id, title, source, amount, period, territory) VALUES (?,?,?,?,?,?)",
            [(statement_id, r.get("title"), r.get("source"), r["amount"],
              r.get("period"), r.get("territory") or "") for r in rows],
        )
    return statement_id


def get_statements(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM statements WHERE user_id = ? ORDER BY uploaded DESC", (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_statement_rows(user_id, statement_id=None):
    q = ("SELECT sr.* FROM statement_rows sr JOIN statements s ON s.id = sr.statement_id "
         "WHERE s.user_id = ?")
    args = [user_id]
    if statement_id:
        q += " AND sr.statement_id = ?"
        args.append(statement_id)
    with get_db() as db:
        rows = db.execute(q, args).fetchall()
    return [dict(r) for r in rows]


# --- Smart links -------------------------------------------------------------

def create_db_link(slug, user_id, title, target, platforms, meta=None):
    base, n = slug, 1
    with get_db() as db:
        while db.execute("SELECT 1 FROM smart_links WHERE slug = ?", (slug,)).fetchone():
            n += 1
            slug = f"{base}-{n}"
        db.execute(
            "INSERT INTO smart_links (slug, user_id, title, target, platforms, meta, created) VALUES (?,?,?,?,?,?,?)",
            (slug, user_id, title, target, json.dumps(platforms or []),
             json.dumps(meta) if meta else None, _now()),
        )
    return slug


def _link_row(d):
    d["platforms"] = json.loads(d.get("platforms") or "[]")
    d["meta"] = json.loads(d["meta"]) if d.get("meta") else None
    return d


def get_db_links(user_id):
    """Every smart link this account owns.

    user_id is required, not optional with a default: this table went out
    unfiltered once, and every signed-in account was served every other
    account's link titles, slugs and destinations on /links. A required
    argument means a caller that forgets it raises here rather than
    quietly returning the whole table.
    """
    with get_db() as db:
        rows = db.execute(
            "SELECT l.*, (SELECT COUNT(*) FROM link_clicks c WHERE c.slug = l.slug) AS clicks "
            "FROM smart_links l WHERE l.user_id = ? ORDER BY created DESC",
            (user_id,)
        ).fetchall()
    return [_link_row(dict(r)) for r in rows]


def get_db_link(slug):
    with get_db() as db:
        row = db.execute("SELECT * FROM smart_links WHERE slug = ?", (slug,)).fetchone()
    return _link_row(dict(row)) if row else None


def log_click(slug):
    with get_db() as db:
        db.execute("INSERT INTO link_clicks (slug, ts) VALUES (?,?)", (slug, _now()))


# --- API cache -----------------------------------------------------------------

def add_catalog_track(user_id, track):
    """Save a Discover track to the user's catalog. Returns the row id,
    or None if the same title+artist is already in their catalog."""
    track_id = uuid.uuid4().hex
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO catalog_tracks (id, user_id, title, artist, album, art, preview, url, added)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (track_id, user_id, (track.get("title") or "").strip(),
                 (track.get("artist") or "").strip(), track.get("album") or "",
                 track.get("art") or "", track.get("preview") or "",
                 track.get("url") or "", _now()),
            )
    except sqlite3.IntegrityError:
        return None
    return track_id


def set_catalog_track_meta(user_id, track_id, meta):
    with get_db() as db:
        db.execute("UPDATE catalog_tracks SET meta = ? WHERE id = ? AND user_id = ?",
                   (json.dumps(meta), track_id, user_id))


def get_catalog_tracks(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM catalog_tracks WHERE user_id = ? ORDER BY added DESC",
            (user_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = json.loads(d["meta"]) if d.get("meta") else None
        out.append(d)
    return out


def remove_catalog_track(user_id, track_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM catalog_tracks WHERE id = ? AND user_id = ?",
                         (track_id, user_id))
    return cur.rowcount > 0


def cache_get(key, max_age_seconds):
    with get_db() as db:
        row = db.execute("SELECT value, created FROM api_cache WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    created = datetime.fromisoformat(row["created"])
    if (datetime.now(timezone.utc) - created).total_seconds() > max_age_seconds:
        return None
    return json.loads(row["value"])


def cache_set(key, value):
    with get_db() as db:
        db.execute(
            "INSERT INTO api_cache (key, value, created) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, created=excluded.created",
            (key, json.dumps(value), _now()),
        )


def get_kv(key, default=None):
    """Plain server-side key/value store (no TTL) — e.g. secrets that must
    survive deploys without a trip through the Render dashboard."""
    with get_db() as db:
        row = db.execute("SELECT value FROM app_kv WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_kv(key, value):
    with get_db() as db:
        db.execute(
            "INSERT INTO app_kv (key, value, updated) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
            (key, value, _now()))


# --- EPK profiles --------------------------------------------------------------

def save_epk(user_id, data):
    with get_db() as db:
        db.execute(
            "INSERT INTO epk_profiles (user_id, data, updated) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
            (user_id, json.dumps(data), _now()),
        )


def save_epk_photo(user_id, photo_path):
    with get_db() as db:
        db.execute(
            "INSERT INTO epk_profiles (user_id, data, photo, updated) VALUES (?, '{}', ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET photo=excluded.photo, updated=excluded.updated",
            (user_id, photo_path, _now()),
        )


def get_epk(user_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM epk_profiles WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return {"data": json.loads(row["data"] or "{}"), "photo": row["photo"],
            "slug": row["slug"]}


def set_epk_slug(user_id, slug):
    with get_db() as db:
        db.execute(
            "INSERT INTO epk_profiles (user_id, data, slug, updated) VALUES (?,'{}',?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET slug=excluded.slug, updated=excluded.updated",
            (user_id, slug, _now()),
        )


def save_epk_asset(user_id, kind, path):
    with get_db() as db:
        db.execute(
            "INSERT INTO epk_assets (user_id, kind, path, public, updated) VALUES (?,?,?,1,?) "
            "ON CONFLICT(user_id, kind) DO UPDATE SET path=excluded.path, updated=excluded.updated",
            (user_id, kind, path, _now()),
        )


def set_epk_asset_public(user_id, kind, public):
    with get_db() as db:
        cur = db.execute("UPDATE epk_assets SET public = ? WHERE user_id = ? AND kind = ?",
                         (1 if public else 0, user_id, kind))
    return cur.rowcount > 0


def get_epk_assets(user_id, public_only=False):
    q = "SELECT * FROM epk_assets WHERE user_id = ?"
    if public_only:
        q += " AND public = 1"
    with get_db() as db:
        rows = db.execute(q, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_epk_by_slug(slug):
    with get_db() as db:
        row = db.execute(
            "SELECT p.*, u.name AS user_name FROM epk_profiles p "
            "JOIN users u ON u.id = p.user_id WHERE p.slug = ?", (slug,)).fetchone()
    if row is None:
        return None
    return {"data": json.loads(row["data"] or "{}"), "photo": row["photo"],
            "slug": row["slug"], "user_id": row["user_id"],
            "user_name": row["user_name"]}


# --- Pulse snapshots (real growth history) ----------------------------------------

def record_pulse_snapshot(user_id, followers, popularity, deezer_fans):
    """One snapshot per user per day; later same-day calls refresh it."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_db() as db:
        db.execute(
            "INSERT INTO pulse_snapshots (user_id, day, followers, popularity, deezer_fans) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, day) DO UPDATE SET followers=excluded.followers, "
            "popularity=excluded.popularity, deezer_fans=excluded.deezer_fans",
            (user_id, day, followers, popularity, deezer_fans))


def list_pulse_snapshots(user_id, limit=90):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM pulse_snapshots WHERE user_id = ? ORDER BY day DESC LIMIT ?",
            (user_id, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def add_pulse_peer(user_id, artist_id, name, image=""):
    with get_db() as db:
        db.execute(
            "INSERT INTO pulse_peers (user_id, artist_id, name, image, created)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(user_id, artist_id) DO UPDATE SET name=excluded.name,"
            " image=excluded.image",
            (user_id, artist_id[:64], name[:120], image[:300], _now()))


def list_pulse_peers(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM pulse_peers WHERE user_id = ? ORDER BY created",
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_pulse_peer(user_id, artist_id):
    with get_db() as db:
        db.execute("DELETE FROM pulse_peers WHERE user_id = ? AND artist_id = ?",
                   (user_id, artist_id))
        db.execute("DELETE FROM pulse_peer_snapshots WHERE user_id = ?"
                   " AND artist_id = ?", (user_id, artist_id))


def record_peer_snapshot(user_id, artist_id, followers, popularity):
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_db() as db:
        db.execute(
            "INSERT INTO pulse_peer_snapshots (user_id, artist_id, day,"
            " followers, popularity) VALUES (?,?,?,?,?)"
            " ON CONFLICT(user_id, artist_id, day) DO UPDATE SET"
            " followers=excluded.followers, popularity=excluded.popularity",
            (user_id, artist_id, day, followers, popularity))


def list_peer_snapshots(user_id, artist_id, limit=90):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM pulse_peer_snapshots WHERE user_id = ?"
            " AND artist_id = ? ORDER BY day DESC LIMIT ?",
            (user_id, artist_id, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


# --- Fan Club ----------------------------------------------------------------------

def save_fan_club(user_id, name, blurb, price_cents, perks, active):
    with get_db() as db:
        db.execute(
            "INSERT INTO fan_clubs (user_id, name, blurb, price_cents, perks, active, updated) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, blurb=excluded.blurb, "
            "price_cents=excluded.price_cents, perks=excluded.perks, active=excluded.active, "
            "updated=excluded.updated",
            (user_id, name[:80], blurb[:500], int(price_cents),
             json.dumps(perks[:8]), 1 if active else 0, _now()))


def get_fan_club(user_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM fan_clubs WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["perks"] = json.loads(d["perks"] or "[]")
    return d


def add_club_member(artist_id, member_email, customer_id, subscription_id):
    member_id = uuid.uuid4().hex
    email = (member_email or "").lower().strip()
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO club_members (id, artist_id, member_email, stripe_customer_id,"
                " stripe_subscription_id, status, created) VALUES (?,?,?,?,?,'active',?)",
                (member_id, artist_id, email, customer_id, subscription_id, _now()))
    except sqlite3.IntegrityError:
        with get_db() as db:
            db.execute(
                "UPDATE club_members SET status='active', stripe_customer_id=?,"
                " stripe_subscription_id=? WHERE artist_id=? AND member_email=?",
                (customer_id, subscription_id, artist_id, email))
        return None
    return member_id


def list_club_members(artist_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM club_members WHERE artist_id = ? ORDER BY created DESC",
            (artist_id,)).fetchall()
    return [dict(r) for r in rows]


def cancel_club_member_by_subscription(subscription_id):
    """Returns the artist_id whose member canceled, or None."""
    with get_db() as db:
        row = db.execute("SELECT artist_id FROM club_members WHERE stripe_subscription_id = ?",
                         (subscription_id,)).fetchone()
        if row:
            db.execute("UPDATE club_members SET status='canceled' "
                       "WHERE stripe_subscription_id = ?", (subscription_id,))
    return row["artist_id"] if row else None


def get_active_club_member(artist_id, member_email):
    email = (member_email or "").lower().strip()
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM club_members WHERE artist_id = ? AND member_email = ? "
            "AND status = 'active'", (artist_id, email)).fetchone()
    return dict(row) if row else None


def add_club_drop(artist_id, title, body, link_url):
    drop_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO club_drops (id, artist_id, title, body, link_url, created) "
            "VALUES (?,?,?,?,?,?)",
            (drop_id, artist_id, title[:120], body[:4000], (link_url or "")[:300], _now()))
    return drop_id


def list_club_drops(artist_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM club_drops WHERE artist_id = ? ORDER BY created DESC",
            (artist_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_club_drop(artist_id, drop_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM club_drops WHERE id = ? AND artist_id = ?",
                         (drop_id, artist_id))
    return cur.rowcount > 0


# --- Tour Hub ----------------------------------------------------------------

def add_tour_show(user_id, date, venue, city, notes):
    show_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_shows (id, user_id, date, venue, city, notes, created) "
            "VALUES (?,?,?,?,?,?,?)",
            (show_id, user_id, date[:10], venue[:120], city[:80], notes[:1000], _now()))
    return show_id


def list_tour_shows(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM tour_shows WHERE user_id = ? ORDER BY date, created",
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def update_tour_show_status(user_id, show_id, status):
    with get_db() as db:
        cur = db.execute("UPDATE tour_shows SET status = ? WHERE id = ? AND user_id = ?",
                         (status, show_id, user_id))
    return cur.rowcount > 0


def delete_tour_show(user_id, show_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM tour_shows WHERE id = ? AND user_id = ?",
                         (show_id, user_id))
    return cur.rowcount > 0


def save_stage_plot(user_id, data):
    with get_db() as db:
        db.execute(
            "INSERT INTO stage_plots (user_id, data, updated) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
            (user_id, json.dumps(data), _now()))


def get_stage_plot(user_id):
    with get_db() as db:
        row = db.execute("SELECT data FROM stage_plots WHERE user_id = ?",
                         (user_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def save_rack_preset(user_id, data):
    with get_db() as db:
        db.execute(
            "INSERT INTO rack_presets (user_id, data, updated) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
            (user_id, json.dumps(data), _now()))


# --- what the Rack measured -------------------------------------------
# The Rack measures a master properly and then the tab closes. These two
# functions are the difference between a meter and a memory: the numbers
# persist, so Release Readiness can speak for the audio instead of only
# for the paperwork around it.

# --- scores over time ---------------------------------------------------
# These recompute on every request and used to be stored nowhere, so the
# app could say where an artist stands and never whether they are getting
# anywhere. One row per score per day: the day's reading is updated in
# place rather than appended, because a score that recalculates on every
# page load would otherwise write hundreds of identical rows a day.

def record_score(user_id, kind, total, detail=None):
    """Upsert today's reading. Never raises into a request."""
    import uuid as _uuid
    try:
        total = float(total)
    except (TypeError, ValueError):
        return
    if total != total:                      # NaN
        return
    now = _now()
    day = now[:10]
    with get_db() as db:
        db.execute(
            "INSERT INTO score_history (id, user_id, kind, day, total, "
            "detail, updated) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id, kind, day) DO UPDATE SET "
            "total=excluded.total, detail=excluded.detail, "
            "updated=excluded.updated",
            (_uuid.uuid4().hex, user_id, kind, day, total,
             json.dumps(detail or {}), now))


def score_trend(user_id, kind, limit=60):
    """Newest first, one row per day."""
    with get_db() as db:
        rows = db.execute(
            "SELECT day, total, detail, updated FROM score_history "
            "WHERE user_id = ? AND kind = ? ORDER BY day DESC LIMIT ?",
            (user_id, kind, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(d["detail"] or "{}")
        except ValueError:
            d["detail"] = {}
        out.append(d)
    return out


def all_score_trends(user_id, limit=60):
    with get_db() as db:
        kinds = [r["kind"] for r in db.execute(
            "SELECT DISTINCT kind FROM score_history WHERE user_id = ?",
            (user_id,)).fetchall()]
    return {k: score_trend(user_id, k, limit) for k in kinds}


def save_track_analysis(user_id, row):
    """Store one measurement pass. Latest wins per (user, filename)."""
    import uuid as _uuid
    keep = ("track_id", "filename", "integrated", "lra", "true_peak",
            "sample_peak", "short_term_max", "momentary_max", "bpm",
            "bpm_confidence", "key", "key_fit", "duration", "sample_rate",
            "channels", "hook_15s", "hook_30s", "first_beat", "bar_seconds",
            "grid_confidence", "engine")
    vals = {k: row.get(k) for k in keep}
    vals["filename"] = (vals.get("filename") or "")[:200]
    vals["key"] = (vals.get("key") or "")[:40]
    vals["track_id"] = (vals.get("track_id") or "")[:80]
    vals["engine"] = (vals.get("engine") or "")[:60]
    with get_db() as db:
        db.execute(
            "DELETE FROM track_analysis WHERE user_id = ? AND filename = ?",
            (user_id, vals["filename"]))
        db.execute(
            "INSERT INTO track_analysis (id, user_id, measured_at, " +
            ", ".join(keep) + ") VALUES (?,?,?," +
            ",".join("?" * len(keep)) + ")",
            (_uuid.uuid4().hex, user_id, _now()) +
            tuple(vals[k] for k in keep))


def get_track_analyses(user_id, limit=50):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM track_analysis WHERE user_id = ? "
            "ORDER BY measured_at DESC LIMIT ?", (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


def latest_track_analysis(user_id):
    """The most recent measurement, or None if the Rack has never run."""
    rows = get_track_analyses(user_id, limit=1)
    return rows[0] if rows else None


def save_light_show(user_id, data):
    with get_db() as db:
        db.execute(
            "INSERT INTO light_shows (user_id, data, updated) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
            (user_id, json.dumps(data), _now()))


def get_light_show(user_id):
    with get_db() as db:
        row = db.execute("SELECT data FROM light_shows WHERE user_id = ?",
                         (user_id,)).fetchone()
    return json.loads(row["data"]) if row else None


MAX_RACK_PRESETS = 40


def list_rack_presets(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT id, name, note, created, updated FROM rack_library "
            "WHERE user_id = ? ORDER BY updated DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_rack_preset_by_id(user_id, preset_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM rack_library WHERE id = ? AND user_id = ?",
                         (preset_id, user_id)).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["data"] = json.loads(d["data"] or "{}")
    except ValueError:
        d["data"] = {}
    return d


def save_rack_preset_named(user_id, preset_id, name, data, note=""):
    """Upsert by id. Saving over a name you already have replaces it rather
    than making a second row with the same label, because two racks called
    "vocal chain" is worse than one."""
    name = (name or "Untitled rack").strip()[:80]
    blob = json.dumps(data if isinstance(data, dict) else {})
    now = _now()
    with get_db() as db:
        row = None
        if preset_id:
            row = db.execute("SELECT id FROM rack_library WHERE id=? AND user_id=?",
                             (preset_id, user_id)).fetchone()
        if row is None:
            row = db.execute("SELECT id FROM rack_library WHERE user_id=? AND lower(name)=lower(?)",
                             (user_id, name)).fetchone()
        if row is not None:
            preset_id = row["id"]
            db.execute("UPDATE rack_library SET name=?, note=?, data=?, updated=? "
                       "WHERE id=? AND user_id=?",
                       (name, (note or "")[:200], blob, now, preset_id, user_id))
        else:
            n = db.execute("SELECT COUNT(*) AS n FROM rack_library WHERE user_id=?",
                           (user_id,)).fetchone()["n"]
            if n >= MAX_RACK_PRESETS:
                return None
            preset_id = uuid.uuid4().hex
            db.execute("INSERT INTO rack_library (id, user_id, name, note, data, created, updated) "
                       "VALUES (?,?,?,?,?,?,?)",
                       (preset_id, user_id, name, (note or "")[:200], blob, now, now))
    return preset_id


def delete_rack_preset(user_id, preset_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM rack_library WHERE id=? AND user_id=?",
                         (preset_id, user_id))
    return cur.rowcount > 0


def get_rack_preset(user_id):
    with get_db() as db:
        row = db.execute("SELECT data FROM rack_presets WHERE user_id = ?",
                         (user_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def _show_dict(row):
    d = dict(row)
    d["advance"] = json.loads(d.get("advance") or "{}")
    d["settlement"] = json.loads(d.get("settlement") or "{}")
    return d


def get_tour_show(user_id, show_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_shows WHERE id = ? AND user_id = ?",
                         (show_id, user_id)).fetchone()
    return _show_dict(row) if row else None


def save_show_advance(user_id, show_id, advance):
    with get_db() as db:
        cur = db.execute("UPDATE tour_shows SET advance = ? WHERE id = ? AND user_id = ?",
                         (json.dumps(advance), show_id, user_id))
    return cur.rowcount > 0


def save_show_settlement(user_id, show_id, settlement):
    with get_db() as db:
        cur = db.execute("UPDATE tour_shows SET settlement = ? WHERE id = ? AND user_id = ?",
                         (json.dumps(settlement), show_id, user_id))
    return cur.rowcount > 0


def set_show_share_token(user_id, show_id, token):
    with get_db() as db:
        cur = db.execute("UPDATE tour_shows SET share_token = ? WHERE id = ? AND user_id = ?",
                         (token, show_id, user_id))
    return cur.rowcount > 0


# --- Asset Vault uploads ----------------------------------------------------------

def add_vault_file(user_id, path, label, kind):
    file_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO vault_files (id, user_id, path, label, kind, created) "
            "VALUES (?,?,?,?,?,?)",
            (file_id, user_id, path[:300], label[:120], kind[:40], _now()))
    return file_id


def list_vault_files(user_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM vault_files WHERE user_id = ? "
                          "ORDER BY created DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_vault_file(user_id, file_id):
    """Removes the record; returns the path so the caller can clean the file."""
    with get_db() as db:
        row = db.execute("SELECT path FROM vault_files WHERE id = ? AND user_id = ?",
                         (file_id, user_id)).fetchone()
        if row is None:
            return None
        db.execute("DELETE FROM vault_files WHERE id = ? AND user_id = ?",
                   (file_id, user_id))
    return row["path"]

# --- EPK pitch share -----------------------------------------------------------

def get_epk_share(user_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM epk_shares WHERE user_id = ?",
                         (user_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["audio"] = json.loads(d["audio"] or "[]")
    return d


def get_epk_share_by_token(token):
    with get_db() as db:
        row = db.execute("SELECT * FROM epk_shares WHERE token = ?",
                         (token,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["audio"] = json.loads(d["audio"] or "[]")
    return d


def upsert_epk_share(user_id, token, pin="", expires="", audio=None):
    with get_db() as db:
        db.execute(
            "INSERT INTO epk_shares (user_id, token, pin, expires, audio, created)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET token=excluded.token,"
            " pin=excluded.pin, expires=excluded.expires, audio=excluded.audio",
            (user_id, token, pin[:16], expires[:10], json.dumps(audio or []),
             _now()))


def delete_epk_share(user_id):
    with get_db() as db:
        row = db.execute("SELECT token FROM epk_shares WHERE user_id = ?",
                         (user_id,)).fetchone()
        db.execute("DELETE FROM epk_shares WHERE user_id = ?", (user_id,))
        if row is not None:
            db.execute("DELETE FROM epk_share_events WHERE token = ?",
                       (row["token"],))


def log_epk_event(token, kind, detail=""):
    with get_db() as db:
        db.execute(
            "INSERT INTO epk_share_events (token, kind, detail, ts) VALUES (?,?,?,?)",
            (token, kind[:20], detail[:120], _now()))


def epk_share_stats(token):
    with get_db() as db:
        views = db.execute(
            "SELECT COUNT(*) AS n FROM epk_share_events WHERE token = ?"
            " AND kind = 'view'", (token,)).fetchone()["n"]
        plays = db.execute(
            "SELECT detail, COUNT(*) AS n FROM epk_share_events WHERE token = ?"
            " AND kind = 'play' GROUP BY detail ORDER BY n DESC",
            (token,)).fetchall()
        last = db.execute(
            "SELECT ts FROM epk_share_events WHERE token = ? AND kind = 'view'"
            " ORDER BY id DESC LIMIT 1", (token,)).fetchone()
    return {"views": views, "plays": [(r["detail"], r["n"]) for r in plays],
            "last_view": last["ts"] if last else ""}


def epk_viewed_today(token, day_prefix):
    with get_db() as db:
        row = db.execute(
            "SELECT 1 FROM epk_share_events WHERE token = ? AND kind = 'view'"
            " AND ts LIKE ? LIMIT 1", (token, day_prefix + "%")).fetchone()
    return row is not None


# --- One-sheet share -----------------------------------------------------------

def get_onesheet_share(user_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM onesheet_shares WHERE user_id = ?",
                         (user_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["audio"] = json.loads(d["audio"] or "[]")
    return d


def get_onesheet_share_by_token(token):
    with get_db() as db:
        row = db.execute("SELECT * FROM onesheet_shares WHERE token = ?",
                         (token,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["audio"] = json.loads(d["audio"] or "[]")
    return d


def upsert_onesheet_share(user_id, token, pin="", banner="", audio=None):
    with get_db() as db:
        db.execute(
            "INSERT INTO onesheet_shares (user_id, token, pin, banner, audio, created)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET token=excluded.token,"
            " pin=excluded.pin, banner=excluded.banner, audio=excluded.audio",
            (user_id, token, pin[:16], banner[:300],
             json.dumps(audio or []), _now()))


def delete_onesheet_share(user_id):
    with get_db() as db:
        row = db.execute("SELECT token FROM onesheet_shares WHERE user_id = ?",
                         (user_id,)).fetchone()
        db.execute("DELETE FROM onesheet_shares WHERE user_id = ?", (user_id,))
        if row is not None:
            db.execute("DELETE FROM onesheet_views WHERE token = ?",
                       (row["token"],))


def log_onesheet_view(token):
    with get_db() as db:
        db.execute("INSERT INTO onesheet_views (token, ts) VALUES (?,?)",
                   (token, _now()))


def onesheet_view_stats(token):
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) AS n FROM onesheet_views WHERE token = ?",
                           (token,)).fetchone()["n"]
        recent = db.execute(
            "SELECT ts FROM onesheet_views WHERE token = ? ORDER BY id DESC LIMIT 20",
            (token,)).fetchall()
    return {"total": total, "recent": [r["ts"] for r in recent]}


# --- Outreach Pipeline (personal CRM) ---------------------------------------------

OUTREACH_STAGES = ("saved", "pitched", "listened", "discussion", "accepted", "passed")


def add_outreach(user_id, contact, role, stage, notes):
    item_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO outreach_items (id, user_id, contact, role, stage,"
            " notes, updated) VALUES (?,?,?,?,?,?,?)",
            (item_id, user_id, contact[:120], role[:60],
             stage if stage in OUTREACH_STAGES else "saved",
             notes[:500], _now()))
    return item_id


def list_outreach(user_id):
    order = {s: i for i, s in enumerate(OUTREACH_STAGES)}
    with get_db() as db:
        rows = db.execute("SELECT * FROM outreach_items WHERE user_id = ? "
                          "ORDER BY updated DESC", (user_id,)).fetchall()
    return sorted([dict(r) for r in rows],
                  key=lambda r: order.get(r["stage"], 0))


def set_outreach_stage(user_id, item_id, stage):
    if stage not in OUTREACH_STAGES:
        return
    with get_db() as db:
        db.execute("UPDATE outreach_items SET stage = ?, updated = ? "
                   "WHERE id = ? AND user_id = ?",
                   (stage, _now(), item_id, user_id))


def delete_outreach(user_id, item_id):
    with get_db() as db:
        db.execute("DELETE FROM outreach_items WHERE id = ? AND user_id = ?",
                   (item_id, user_id))


# --- Collaboration Marketplace ----------------------------------------------------

def add_collab_request(user_id, role, genre, kind, title, details, terms,
                       ref_url, closes):
    req_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO collab_requests (id, user_id, role, genre, kind, title,"
            " details, terms, ref_url, closes, created) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (req_id, user_id, role[:60], genre[:60], kind, title[:120],
             details[:1000], terms[:120], ref_url[:300], closes[:10], _now()))
    return req_id


def list_collab_requests(kind=None, role=None, genre=None):
    """Open requests, newest first, with the poster's name attached."""
    q = ("SELECT c.*, u.name AS poster_name FROM collab_requests c "
         "JOIN users u ON u.id = c.user_id WHERE c.status = 'open'")
    args = []
    if kind in ("bid", "split", "fun"):
        q += " AND c.kind = ?"
        args.append(kind)
    if role:
        q += " AND c.role = ?"
        args.append(role)
    if genre:
        q += " AND c.genre = ?"
        args.append(genre)
    q += " ORDER BY c.created DESC LIMIT 200"
    with get_db() as db:
        rows = db.execute(q, args).fetchall()
    return [dict(r) for r in rows]


def get_collab_request(req_id):
    with get_db() as db:
        row = db.execute(
            "SELECT c.*, u.name AS poster_name FROM collab_requests c "
            "JOIN users u ON u.id = c.user_id WHERE c.id = ?",
            (req_id,)).fetchone()
    return dict(row) if row else None


def list_own_collab_requests(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM collab_requests WHERE user_id = ? "
            "ORDER BY created DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def close_collab_request(user_id, req_id):
    with get_db() as db:
        db.execute("UPDATE collab_requests SET status = 'closed' "
                   "WHERE id = ? AND user_id = ?", (req_id, user_id))


def delete_collab_request(user_id, req_id):
    with get_db() as db:
        db.execute("DELETE FROM collab_requests WHERE id = ? AND user_id = ?",
                   (req_id, user_id))
        db.execute("DELETE FROM collab_replies WHERE request_id = ?", (req_id,))


def add_collab_reply(req_id, user_id, message, contact, proposal, ref_url):
    with get_db() as db:
        db.execute(
            "INSERT INTO collab_replies (id, request_id, user_id, message,"
            " contact, proposal, ref_url, created) VALUES (?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, req_id, user_id, message[:1000], contact[:120],
             proposal[:120], ref_url[:300], _now()))


def list_collab_replies(req_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT r.*, u.name AS applicant_name FROM collab_replies r "
            "JOIN users u ON u.id = r.user_id WHERE r.request_id = ? "
            "ORDER BY r.created", (req_id,)).fetchall()
    return [dict(r) for r in rows]


def toggle_collab_save(user_id, req_id):
    """Bookmark toggle -> True when now saved."""
    with get_db() as db:
        cur = db.execute("DELETE FROM collab_saves WHERE user_id = ? "
                         "AND request_id = ?", (user_id, req_id))
        if cur.rowcount:
            return False
        db.execute("INSERT INTO collab_saves (user_id, request_id, created) "
                   "VALUES (?,?,?)", (user_id, req_id, _now()))
        return True


def list_collab_saves(user_id):
    with get_db() as db:
        rows = db.execute("SELECT request_id FROM collab_saves WHERE user_id = ?",
                          (user_id,)).fetchall()
    return {r["request_id"] for r in rows}


def add_board_listing(user_id, kind, title, region, window, genre, details):
    listing_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_board (id, user_id, kind, title, region, window,"
            " genre, details, created) VALUES (?,?,?,?,?,?,?,?,?)",
            (listing_id, user_id, kind, title[:120], region[:80], window[:80],
             genre[:60], details[:1000], _now()))
    return listing_id


def list_board_listings(kind=None):
    """Open listings, newest first, with the poster's name attached."""
    q = ("SELECT b.*, u.name AS poster_name FROM tour_board b "
         "JOIN users u ON u.id = b.user_id WHERE b.status = 'open'")
    args = []
    if kind in ("artist", "venue"):
        q += " AND b.kind = ?"
        args.append(kind)
    q += " ORDER BY b.created DESC LIMIT 200"
    with get_db() as db:
        rows = db.execute(q, args).fetchall()
    return [dict(r) for r in rows]


def get_board_listing(listing_id):
    with get_db() as db:
        row = db.execute(
            "SELECT b.*, u.name AS poster_name FROM tour_board b "
            "JOIN users u ON u.id = b.user_id WHERE b.id = ?",
            (listing_id,)).fetchone()
    return dict(row) if row else None


def close_board_listing(user_id, listing_id):
    with get_db() as db:
        cur = db.execute("UPDATE tour_board SET status = 'closed' "
                         "WHERE id = ? AND user_id = ?", (listing_id, user_id))
    return cur.rowcount > 0


def delete_board_listing(user_id, listing_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM tour_board WHERE id = ? AND user_id = ?",
                         (listing_id, user_id))
        if cur.rowcount:
            db.execute("DELETE FROM tour_board_replies WHERE listing_id = ?",
                       (listing_id,))
    return cur.rowcount > 0


def list_own_board_listings(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM tour_board WHERE user_id = ? ORDER BY created DESC",
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def add_board_reply(listing_id, from_user_id, message, contact):
    reply_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_board_replies (id, listing_id, from_user_id,"
            " message, contact, created) VALUES (?,?,?,?,?,?)",
            (reply_id, listing_id, from_user_id, message[:1000], contact[:200], _now()))
    return reply_id


def list_board_replies(listing_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT r.*, u.name AS from_name FROM tour_board_replies r "
            "JOIN users u ON u.id = r.from_user_id WHERE r.listing_id = ? "
            "ORDER BY r.created", (listing_id,)).fetchall()
    return [dict(r) for r in rows]


def ensure_ref_code(user_id):
    with get_db() as db:
        row = db.execute("SELECT ref_code FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        if row["ref_code"]:
            return row["ref_code"]
        code = uuid.uuid4().hex[:8]
        db.execute("UPDATE users SET ref_code = ? WHERE id = ?", (code, user_id))
    return code


def user_by_ref_code(code):
    if not code:
        return None
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE ref_code = ?", (code,)).fetchone()
    return dict(row) if row else None


def set_referred_by(user_id, referrer_id):
    with get_db() as db:
        db.execute("UPDATE users SET referred_by = ? WHERE id = ? AND referred_by IS NULL",
                   (referrer_id, user_id))


def mark_ref_credited(user_id):
    with get_db() as db:
        db.execute("UPDATE users SET ref_credited = 1 WHERE id = ?", (user_id,))


def list_uncredited_referrals(referrer_id):
    """Referred users who converted to a real paid subscription but whose
    referrer credit hasn't been applied yet."""
    with get_db() as db:
        rows = db.execute(
            "SELECT id, email FROM users WHERE referred_by = ? AND ref_credited = 0 "
            "AND stripe_subscription_id IS NOT NULL", (referrer_id,)).fetchall()
    return [dict(r) for r in rows]


def referral_stats(referrer_id):
    with get_db() as db:
        signups = db.execute("SELECT COUNT(*) AS n FROM users WHERE referred_by = ?",
                             (referrer_id,)).fetchone()["n"]
        converted = db.execute(
            "SELECT COUNT(*) AS n FROM users WHERE referred_by = ? AND ref_credited = 1",
            (referrer_id,)).fetchone()["n"]
    return {"signups": signups, "converted": converted}


# --- Beats: registry, licences, cleared list, usage cases ---------------------
# The producer side. A licence has two ends, so every read here is keyed
# on who is asking: the producer who owns the beat, or the licensee whose
# email the licence names.

def add_beat(user_id, title, bpm="", song_key="", tags="", note=""):
    beat_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO beats (id, user_id, title, bpm, song_key, tags, note,"
            " created) VALUES (?,?,?,?,?,?,?,?)",
            (beat_id, user_id, title[:200], bpm[:20], song_key[:20],
             tags[:200], note[:600], _now()))
    return beat_id


def list_beats(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM beats WHERE user_id = ? ORDER BY created DESC",
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_beat(beat_id, user_id=None):
    q = "SELECT * FROM beats WHERE id = ?"
    args = [beat_id]
    if user_id:
        q += " AND user_id = ?"
        args.append(user_id)
    with get_db() as db:
        row = db.execute(q, args).fetchone()
    return dict(row) if row else None


def update_beat(user_id, beat_id, fields):
    """Edit the registry row. Only the columns a producer types."""
    allowed = ("title", "bpm", "song_key", "tags", "note")
    sets, args = [], []
    for k in allowed:
        if k in fields:
            sets.append("%s = ?" % k)
            args.append(str(fields[k] or "")[:600])
    if not sets:
        return False
    args += [beat_id, user_id]
    with get_db() as db:
        cur = db.execute("UPDATE beats SET %s WHERE id = ? AND user_id = ?"
                         % ", ".join(sets), args)
    return cur.rowcount > 0


def delete_beat(user_id, beat_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM beats WHERE id = ? AND user_id = ?",
                         (beat_id, user_id))
        if cur.rowcount:
            db.execute("DELETE FROM beat_licences WHERE beat_id = ?", (beat_id,))
            db.execute("DELETE FROM beat_clearances WHERE beat_id = ?", (beat_id,))
            db.execute("DELETE FROM beat_uses WHERE beat_id = ?", (beat_id,))
            # A live link to a deleted beat would still play it.
            db.execute("DELETE FROM beat_audio WHERE beat_id = ?", (beat_id,))
            db.execute("DELETE FROM beat_shares WHERE beat_id = ?", (beat_id,))
        return bool(cur.rowcount)


# --- Beat audio: the file, and what the browser measured from it -------------
# Analysis runs in the browser (static/js/tempokey.js — the same detector
# the Rack uses), so no audio is decoded server-side and no third party
# hears the beat. What lands here is a measurement the producer can see
# and override, never a claim the server made on its own.

# Must stay UNDER app.config["MAX_CONTENT_LENGTH"] (25 MB). Flask rejects
# an oversize request before routing, so a ceiling above that one would be
# a number this code prints and never enforces: the producer would get a
# bare 413 instead of a sentence telling them what to do. A 3-minute 24/48
# stereo WAV is ~50 MB, so beats of that size have to be bounced to MP3 or
# FLAC first — which the drop zone says out loud.
MAX_BEAT_BYTES = 24 * 1024 * 1024


def save_beat_audio(user_id, beat_id, row):
    """Upsert. One recording per beat: a re-upload replaces the old row,
    because a beat is one file with one tempo, not a version history."""
    if get_beat(beat_id, user_id) is None:
        return None
    with get_db() as db:
        db.execute("DELETE FROM beat_audio WHERE beat_id = ?", (beat_id,))
        db.execute(
            "INSERT INTO beat_audio (beat_id, user_id, filename, path, mime, bytes,"
            " duration, peaks, bpm, bpm_confidence, bpm_alternates, song_key, key_fit,"
            " key_runner_up, sample_rate, created)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (beat_id, user_id, (row.get("filename") or "")[:200],
             (row.get("path") or "")[:400], (row.get("mime") or "")[:80],
             int(row.get("bytes") or 0), row.get("duration"),
             json.dumps(row.get("peaks") or [])[:60000],
             row.get("bpm"), row.get("bpm_confidence"),
             (row.get("bpm_alternates") or "")[:60],
             (row.get("song_key") or "")[:40], row.get("key_fit"),
             (row.get("key_runner_up") or "")[:40], row.get("sample_rate"), _now()))
    return beat_id


def get_beat_audio(beat_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM beat_audio WHERE beat_id = ?", (beat_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["peaks"] = json.loads(d.get("peaks") or "[]")
    except ValueError:
        d["peaks"] = []
    return d


def beat_audio_for(user_id):
    """Every beat's audio in one read, so the list page does not fire one
    query per row."""
    with get_db() as db:
        rows = db.execute("SELECT * FROM beat_audio WHERE user_id = ?", (user_id,)).fetchall()
    out = {}
    for r in rows:
        d = dict(r)
        try:
            d["peaks"] = json.loads(d.get("peaks") or "[]")
        except ValueError:
            d["peaks"] = []
        out[d["beat_id"]] = d
    return out


def delete_beat_audio(user_id, beat_id):
    with get_db() as db:
        row = db.execute("SELECT path FROM beat_audio WHERE beat_id=? AND user_id=?",
                         (beat_id, user_id)).fetchone()
        if row is None:
            return None
        db.execute("DELETE FROM beat_audio WHERE beat_id=? AND user_id=?", (beat_id, user_id))
    return row["path"]


# --- Private beat links -------------------------------------------------------
# A producer sends one beat to one artist. The link carries that beat and
# nothing else about the catalogue, it can be revoked, and it can lapse.

def create_beat_share(user_id, beat_id, label="", days=0):
    if get_beat(beat_id, user_id) is None:
        return None
    token = uuid.uuid4().hex
    expires = ""
    try:
        days = int(days or 0)
    except (TypeError, ValueError):
        days = 0
    if days > 0:
        expires = (datetime.now(timezone.utc) + timedelta(days=min(days, 365))).isoformat()
    with get_db() as db:
        db.execute("INSERT INTO beat_shares (token, beat_id, user_id, label, expires,"
                   " plays, last_played, created, revoked) VALUES (?,?,?,?,?,0,'',?,0)",
                   (token, beat_id, user_id, (label or "").strip()[:80], expires, _now()))
    return token


def list_beat_shares(user_id, beat_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM beat_shares WHERE user_id=? AND beat_id=? AND revoked=0"
                          " ORDER BY created DESC", (user_id, beat_id)).fetchall()
    return [dict(r) for r in rows]


def get_beat_share(token):
    """No user argument on purpose: the token is the authorisation. A
    revoked link, a lapsed one, or one whose beat was deleted is dead."""
    if not token:
        return None
    with get_db() as db:
        row = db.execute("SELECT * FROM beat_shares WHERE token=? AND revoked=0",
                         (token,)).fetchone()
        if row is None:
            return None
        beat = db.execute("SELECT * FROM beats WHERE id=?", (row["beat_id"],)).fetchone()
    if beat is None:
        return None
    if row["expires"]:
        try:
            when = datetime.fromisoformat(row["expires"].replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > when:
                return None
        except (ValueError, AttributeError):
            return None
    d = dict(row)
    d["beat"] = dict(beat)
    return d


def revoke_beat_share(user_id, token):
    with get_db() as db:
        cur = db.execute("UPDATE beat_shares SET revoked=1 WHERE token=? AND user_id=?",
                         (token, user_id))
    return cur.rowcount > 0


def count_beat_share_play(token):
    """The producer's one honest signal that the link was opened. It
    counts plays, not opens, because a page load is not interest."""
    with get_db() as db:
        db.execute("UPDATE beat_shares SET plays = plays + 1, last_played = ?"
                   " WHERE token = ? AND revoked = 0", (_now(), token))


def add_beat_licence(beat_id, producer_id, fields):
    licence_id = uuid.uuid4().hex
    token = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO beat_licences (id, beat_id, producer_id, licensee_name,"
            " licensee_email, licence_type, territory, term, fee, producer_split,"
            " terms, status, token, created)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (licence_id, beat_id, producer_id,
             (fields.get("licensee_name") or "")[:120],
             (fields.get("licensee_email") or "").strip().lower()[:200],
             fields.get("licence_type") or "lease",
             (fields.get("territory") or "Worldwide")[:80],
             (fields.get("term") or "")[:80],
             float(fields.get("fee") or 0),
             float(fields.get("producer_split") or 50),
             (fields.get("terms") or "")[:2000],
             "sent" if fields.get("send") else "draft", token, _now()))
    return licence_id


def list_beat_licences(beat_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM beat_licences WHERE beat_id = ? ORDER BY created DESC",
            (beat_id,)).fetchall()
    return [dict(r) for r in rows]


def licences_for_licensee(email):
    """The other end of the licence: what this person has been granted."""
    with get_db() as db:
        rows = db.execute(
            "SELECT l.*, b.title AS beat_title, u.name AS producer_name"
            " FROM beat_licences l JOIN beats b ON b.id = l.beat_id"
            " JOIN users u ON u.id = l.producer_id"
            " WHERE l.licensee_email = ? ORDER BY l.created DESC",
            ((email or "").strip().lower(),)).fetchall()
    return [dict(r) for r in rows]


def get_beat_licence_by_token(token):
    with get_db() as db:
        row = db.execute(
            "SELECT l.*, b.title AS beat_title, b.bpm, b.song_key,"
            " u.name AS producer_name FROM beat_licences l"
            " JOIN beats b ON b.id = l.beat_id JOIN users u ON u.id = l.producer_id"
            " WHERE l.token = ?", (token,)).fetchone()
    return dict(row) if row else None


def sign_beat_licence(token, signed_by):
    with get_db() as db:
        cur = db.execute(
            "UPDATE beat_licences SET status = 'signed', signed_by = ?,"
            " signed_at = ? WHERE token = ? AND status != 'signed'",
            (signed_by[:120], _now(), token))
        return bool(cur.rowcount)


def set_beat_licence_status(producer_id, licence_id, status):
    with get_db() as db:
        cur = db.execute(
            "UPDATE beat_licences SET status = ? WHERE id = ? AND producer_id = ?",
            (status, licence_id, producer_id))
        return bool(cur.rowcount)


def add_beat_clearance(beat_id, kind, value, note="", licence_id=""):
    row_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO beat_clearances (id, beat_id, licence_id, kind, value,"
            " note, created) VALUES (?,?,?,?,?,?,?)",
            (row_id, beat_id, licence_id, kind, value.strip()[:300],
             note[:300], _now()))
    return row_id


def list_beat_clearances(beat_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM beat_clearances WHERE beat_id = ? ORDER BY created DESC",
            (beat_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_beat_clearance(beat_id, row_id):
    with get_db() as db:
        cur = db.execute(
            "DELETE FROM beat_clearances WHERE id = ? AND beat_id = ?",
            (row_id, beat_id))
        return bool(cur.rowcount)


def add_beat_use(beat_id, user_id, fields):
    use_id = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO beat_uses (id, beat_id, user_id, url, platform,"
            " found_via, status, notes, created, updated)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (use_id, beat_id, user_id, (fields.get("url") or "")[:600],
             (fields.get("platform") or "")[:60],
             fields.get("found_via") or "manual",
             fields.get("status") or "open",
             (fields.get("notes") or "")[:1000], now, now))
    return use_id


def list_beat_uses(user_id, beat_id=None):
    q = "SELECT u.*, b.title AS beat_title FROM beat_uses u JOIN beats b ON b.id = u.beat_id WHERE u.user_id = ?"
    args = [user_id]
    if beat_id:
        q += " AND u.beat_id = ?"
        args.append(beat_id)
    q += (" ORDER BY CASE u.status WHEN 'open' THEN 0 WHEN 'contacted' THEN 1"
          " WHEN 'invoiced' THEN 2 ELSE 3 END, u.updated DESC")
    with get_db() as db:
        rows = db.execute(q, args).fetchall()
    return [dict(r) for r in rows]


def update_beat_use(user_id, use_id, fields):
    sets, vals = [], []
    for key in ("status", "notes", "platform", "url"):
        if key in fields:
            sets.append("%s = ?" % key)
            vals.append(fields[key])
    if "resolved_amount" in fields:
        sets.append("resolved_amount = ?")
        vals.append(fields["resolved_amount"])
    if not sets:
        return False
    sets.append("updated = ?")
    vals.extend([_now(), use_id, user_id])
    with get_db() as db:
        cur = db.execute(
            "UPDATE beat_uses SET %s WHERE id = ? AND user_id = ?" % ", ".join(sets),
            vals)
        return bool(cur.rowcount)


def add_sign_token(token, user_id, track_id, doc_key, email):
    with get_db() as db:
        db.execute(
            "INSERT INTO sign_tokens (token, user_id, track_id, doc_key, email,"
            " created) VALUES (?,?,?,?,?,?)",
            (token, user_id, track_id, doc_key, email.lower(), _now()))


def get_sign_token(token):
    with get_db() as db:
        row = db.execute(
            "SELECT s.*, u.name AS artist_name FROM sign_tokens s "
            "JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (token,)).fetchone()
    return dict(row) if row else None


def use_sign_token(token):
    with get_db() as db:
        db.execute("UPDATE sign_tokens SET used = 1 WHERE token = ?", (token,))


def _os_track_dict(row):
    d = dict(row)
    d["passport"] = json.loads(d.get("passport") or "{}")
    d["lockbox"] = json.loads(d.get("lockbox") or "{}")
    return d


def add_os_track(user_id, title, release_title="", release_date=""):
    track_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO os_tracks (id, user_id, title, release_title,"
            " release_date, created) VALUES (?,?,?,?,?,?)",
            (track_id, user_id, title[:120], release_title[:120],
             release_date[:10], _now()))
    return track_id


def list_os_tracks(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM os_tracks WHERE user_id = ? ORDER BY created DESC",
            (user_id,)).fetchall()
    return [_os_track_dict(r) for r in rows]


def get_os_track(user_id, track_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM os_tracks WHERE id = ? AND user_id = ?",
                         (track_id, user_id)).fetchone()
    return _os_track_dict(row) if row else None


def update_os_track_passport(user_id, track_id, passport):
    with get_db() as db:
        cur = db.execute("UPDATE os_tracks SET passport = ? WHERE id = ? AND user_id = ?",
                         (json.dumps(passport), track_id, user_id))
    return cur.rowcount > 0


def update_os_track_lockbox(user_id, track_id, lockbox):
    with get_db() as db:
        cur = db.execute("UPDATE os_tracks SET lockbox = ? WHERE id = ? AND user_id = ?",
                         (json.dumps(lockbox), track_id, user_id))
    return cur.rowcount > 0


def delete_os_track(user_id, track_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM os_tracks WHERE id = ? AND user_id = ?",
                         (track_id, user_id))
    return cur.rowcount > 0


def add_roster_invite(label_id, email):
    email = email.lower().strip()
    member_id, token = uuid.uuid4().hex, uuid.uuid4().hex
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO roster_members (id, label_id, email, invite_token, created) "
                "VALUES (?,?,?,?,?)", (member_id, label_id, email, token, _now()))
    except sqlite3.IntegrityError:
        with get_db() as db:
            row = db.execute("SELECT * FROM roster_members WHERE label_id = ? AND email = ?",
                             (label_id, email)).fetchone()
        return dict(row) if row else None
    return {"id": member_id, "email": email, "invite_token": token,
            "status": "invited"}


def get_roster_invite(token):
    with get_db() as db:
        row = db.execute(
            "SELECT r.*, u.name AS label_name FROM roster_members r "
            "JOIN users u ON u.id = r.label_id "
            "WHERE r.invite_token = ? AND r.status = 'invited'", (token,)).fetchone()
    return dict(row) if row else None


def accept_roster_invite(token, artist_user_id):
    with get_db() as db:
        cur = db.execute(
            "UPDATE roster_members SET artist_user_id = ?, status = 'active' "
            "WHERE invite_token = ? AND status = 'invited'",
            (artist_user_id, token))
    return cur.rowcount > 0


def list_roster(label_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT r.*, u.name AS artist_name, u.plan AS artist_plan "
            "FROM roster_members r LEFT JOIN users u ON u.id = r.artist_user_id "
            "WHERE r.label_id = ? ORDER BY r.created", (label_id,)).fetchall()
    return [dict(r) for r in rows]


def get_roster_member(label_id, artist_user_id):
    with get_db() as db:
        row = db.execute(
            "SELECT r.*, u.name AS artist_name FROM roster_members r "
            "JOIN users u ON u.id = r.artist_user_id "
            "WHERE r.label_id = ? AND r.artist_user_id = ? AND r.status = 'active'",
            (label_id, artist_user_id)).fetchone()
    return dict(row) if row else None


def remove_roster_member(label_id, member_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM roster_members WHERE id = ? AND label_id = ?",
                         (member_id, label_id))
    return cur.rowcount > 0


def get_show_by_share_token(token):
    with get_db() as db:
        row = db.execute(
            "SELECT s.*, u.name AS artist_name FROM tour_shows s "
            "JOIN users u ON u.id = s.user_id WHERE s.share_token = ?",
            (token,)).fetchone()
    return _show_dict(row) if row else None


def list_portal_memberships(member_user_id):
    """Teams this user belongs to (active), with the owner's name."""
    with get_db() as db:
        rows = db.execute(
            "SELECT t.owner_id, t.role, u.name AS owner_name FROM team_members t "
            "JOIN users u ON u.id = t.owner_id "
            "WHERE t.member_user_id = ? AND t.status = 'active' ORDER BY t.created",
            (member_user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_portal_membership(member_user_id, owner_id):
    with get_db() as db:
        row = db.execute(
            "SELECT t.*, u.name AS owner_name FROM team_members t "
            "JOIN users u ON u.id = t.owner_id "
            "WHERE t.member_user_id = ? AND t.owner_id = ? AND t.status = 'active'",
            (member_user_id, owner_id)).fetchone()
    return dict(row) if row else None


# --- Statement drop-box tokens ------------------------------------------------------

def get_or_create_ingest_token(user_id):
    with get_db() as db:
        row = db.execute("SELECT token FROM ingest_tokens WHERE user_id = ?",
                         (user_id,)).fetchone()
        if row:
            return row["token"]
        token = "sb-" + uuid.uuid4().hex[:16]
        db.execute("INSERT INTO ingest_tokens (user_id, token, created) VALUES (?,?,?)",
                   (user_id, token, _now()))
    return token


def user_by_ingest_token(token):
    with get_db() as db:
        row = db.execute("SELECT user_id FROM ingest_tokens WHERE token = ?",
                         ((token or "").lower().strip(),)).fetchone()
    return row["user_id"] if row else None


# --- Disputes ----------------------------------------------------------------------

def add_dispute(user_id, platform, dispute_type, description, amount):
    dispute_id = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO disputes (id, user_id, platform, dispute_type, description,"
            " amount, status, created, updated) VALUES (?,?,?,?,?,?,'open',?,?)",
            (dispute_id, user_id, platform[:60], dispute_type[:40],
             description[:1000], float(amount or 0), now, now))
    return dispute_id


def list_disputes(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM disputes WHERE user_id = ? ORDER BY "
            "CASE status WHEN 'open' THEN 0 WHEN 'submitted' THEN 1 ELSE 2 END, "
            "updated DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def set_dispute_status(user_id, dispute_id, status):
    with get_db() as db:
        cur = db.execute(
            "UPDATE disputes SET status = ?, updated = ? WHERE id = ? AND user_id = ?",
            (status, _now(), dispute_id, user_id))
    return cur.rowcount > 0


# --- Team ------------------------------------------------------------------------

def add_team_invite(owner_id, email, role, seat_limit=None):
    """Create an invite without exceeding the owner's team allowance.

    The seat check and insert run under one SQLite write lock so concurrent
    invite requests cannot push an account past its limit. Returns None for
    a duplicate email and a full error object when no seat remains.
    """
    member_id = uuid.uuid4().hex
    token = uuid.uuid4().hex
    try:
        with get_db() as db:
            if seat_limit is not None:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute(
                    "SELECT COUNT(*) FROM team_members WHERE owner_id = ?",
                    (owner_id,),
                ).fetchone()[0]
                if count >= seat_limit:
                    return {"error": "full"}
            db.execute(
                "INSERT INTO team_members (id, owner_id, email, role, status, invite_token, created) "
                "VALUES (?,?,?,?,'invited',?,?)",
                (member_id, owner_id, email.lower().strip(), role, token, _now()))
    except sqlite3.IntegrityError:
        return None
    return {"id": member_id, "invite_token": token}


def list_team(owner_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT t.*, u.name AS member_name FROM team_members t "
            "LEFT JOIN users u ON u.id = t.member_user_id "
            "WHERE t.owner_id = ? ORDER BY t.created", (owner_id,)).fetchall()
    return [dict(r) for r in rows]


def get_team_invite(token):
    with get_db() as db:
        row = db.execute(
            "SELECT t.*, u.name AS owner_name FROM team_members t "
            "JOIN users u ON u.id = t.owner_id "
            "WHERE t.invite_token = ? AND t.status = 'invited'", (token,)).fetchone()
    return dict(row) if row else None


def accept_team_invite(token, member_user_id):
    with get_db() as db:
        cur = db.execute(
            "UPDATE team_members SET status = 'active', member_user_id = ?, "
            "joined = ?, invite_token = NULL WHERE invite_token = ? AND status = 'invited'",
            (member_user_id, _now(), token))
    return cur.rowcount > 0


def remove_team_member(owner_id, member_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM team_members WHERE id = ? AND owner_id = ?",
                         (member_id, owner_id))
    return cur.rowcount > 0


# --- Artist Pulse ---------------------------------------------------------------

def save_pulse_profile(user_id, artist_id, artist_name, artist_image=""):
    with get_db() as db:
        db.execute(
            "INSERT INTO pulse_profiles (user_id, artist_id, artist_name, artist_image, updated) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET artist_id=excluded.artist_id, "
            "artist_name=excluded.artist_name, artist_image=excluded.artist_image, "
            "updated=excluded.updated",
            (user_id, artist_id, artist_name, artist_image, _now()),
        )


def get_pulse_profile(user_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM pulse_profiles WHERE user_id = ?",
                         (user_id,)).fetchone()
    return dict(row) if row else None


def clear_pulse_profile(user_id):
    with get_db() as db:
        db.execute("DELETE FROM pulse_profiles WHERE user_id = ?", (user_id,))


# --- Inbox -------------------------------------------------------------------

def add_inbox(kind, payload, user_id=""):
    """Record a submission against the account it belongs to.

    `user_id` is the account whose inbox this lands in: the artist who
    was pitched, the rights holder whose pack was asked about, the
    person who sent the enquiry. Platform-level rows (demo access
    requests) pass nothing and are visible only to an owner account.
    """
    with get_db() as db:
        db.execute(
            "INSERT INTO inbox (id, user_id, kind, payload, created)"
            " VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex, user_id or "", kind, json.dumps(payload), _now()),
        )


# --- Artist Signal Profile ---------------------------------------------------
# One profile per user: the priorities they set on the homepage Artist EQ,
# validated by the API before it ever reaches here. Payload is the canonical
# profile dict; `updated` mirrors its updatedAt for cheap staleness checks.

def set_artist_signal_profile(user_id, profile):
    with get_db() as db:
        db.execute(
            "INSERT INTO artist_signal_profiles (user_id, payload, updated) "
            "VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "payload = excluded.payload, updated = excluded.updated",
            (user_id, json.dumps(profile), _now()),
        )


def get_artist_signal_profile(user_id):
    with get_db() as db:
        row = db.execute(
            "SELECT payload, updated FROM artist_signal_profiles "
            "WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return None
    try:
        profile = json.loads(row["payload"])
    except Exception:
        return None
    profile["_updated"] = row["updated"]
    return profile


def get_inbox(user_id=None, unowned=False):
    """One account's submissions, newest first, payload always a dict.

    `user_id=None` returns every row and is for owner tooling only.
    `unowned=True` adds the platform-level rows that belong to no
    account, which is what an owner sees on their own page.

    The payload decode is defensive: a row written already-encoded
    comes back as a string, the template calls .items() on it, and the
    whole page 500s. A submission that arrived is worth showing even
    when its shape is odd, and it is certainly not worth hiding the
    other submissions over.
    """
    with get_db() as db:
        if user_id is None:
            rows = db.execute(
                "SELECT * FROM inbox ORDER BY created DESC").fetchall()
        elif unowned:
            rows = db.execute(
                "SELECT * FROM inbox WHERE user_id = ? OR user_id = ''"
                " ORDER BY created DESC", (user_id,)).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM inbox WHERE user_id = ? ORDER BY created DESC",
                (user_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = _decode_payload(d.get("payload"))
        out.append(d)
    return out


def _decode_payload(raw):
    for _ in range(2):  # one extra pass for a double-encoded row
        if isinstance(raw, dict):
            return raw
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            break
    if isinstance(raw, dict):
        return raw
    return {"payload": raw} if raw not in (None, "") else {}

# --- Notifications -------------------------------------------------------------

def notify(user_id, kind, title, body="", link=""):
    with get_db() as db:
        db.execute(
            "INSERT INTO notifications (user_id, kind, title, body, link, created)"
            " VALUES (?,?,?,?,?,?)",
            (user_id, kind, title[:200], body[:400], link[:300], _now()))


def list_notifications(user_id, limit=50):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


def unread_notifications(user_id):
    with get_db() as db:
        row = db.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
            (user_id,)).fetchone()
    return row["n"]


def mark_notifications_read(user_id):
    with get_db() as db:
        db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))

# --- Documents vault -----------------------------------------------------------

def add_document(user_id, filename, path, doc_type, note="", track=""):
    doc_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO documents (id, user_id, filename, path, doc_type, note,"
            " track, created) VALUES (?,?,?,?,?,?,?,?)",
            (doc_id, user_id, filename[:200], path, doc_type[:60], note[:300],
             (track or "")[:200], _now()))
    return doc_id


def list_documents(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM documents WHERE user_id = ? ORDER BY created DESC",
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_document(user_id, doc_id):
    with get_db() as db:
        row = db.execute("SELECT path FROM documents WHERE id = ? AND user_id = ?",
                         (doc_id, user_id)).fetchone()
        if row is None:
            return None
        db.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
    return row["path"]

# --- Recovery cases + deal room --------------------------------------------------

def create_recovery_case(user_id, fields):
    case_id = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO recovery_cases (id, user_id, title, category, estimated_amount,"
            " confidence, status, deadline, notes, created, updated)"
            " VALUES (?,?,?,?,?,?,'open',?,?,?,?)",
            (case_id, user_id, fields.get("title", "Untitled case")[:200],
             fields.get("category", "other")[:40],
             float(fields.get("estimated_amount") or 0),
             fields.get("confidence", "medium")[:10],
             fields.get("deadline", "")[:10], fields.get("notes", "")[:600],
             now, now))
    return case_id


def update_recovery_case(user_id, case_id, fields):
    allowed = ("status", "notes", "deadline", "evidence_doc_id", "payout_result")
    sets, vals = [], []
    for key in allowed:
        if key in fields:
            sets.append("%s = ?" % key)
            vals.append(fields[key])
    if not sets:
        return False
    if fields.get("status") in ("won", "lost", "closed"):
        sets.append("closed_at = ?")
        vals.append(_now())
    sets.append("updated = ?")
    vals.extend([_now(), case_id, user_id])
    with get_db() as db:
        cur = db.execute("UPDATE recovery_cases SET %s WHERE id = ? AND user_id = ?"
                         % ", ".join(sets), vals)
    return cur.rowcount > 0


def list_recovery_cases(user_id):
    with get_db() as db:
        rows = db.execute(
            # Open first, then by what the case is actually worth. Ordering
            # by last-touched put a $4 case above a $4,000 one purely
            # because someone had opened it more recently, and this list is
            # worked from the top down.
            "SELECT * FROM recovery_cases WHERE user_id = ? ORDER BY"
            " CASE status WHEN 'open' THEN 0 WHEN 'submitted' THEN 1 ELSE 2 END,"
            " estimated_amount DESC, updated DESC",
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_recovery_case(user_id, case_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM recovery_cases WHERE id = ? AND user_id = ?",
                         (case_id, user_id)).fetchone()
    return dict(row) if row else None


def create_deal(user_id, fields):
    deal_id = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO deals (id, user_id, deal_type, title, counterparty, status,"
            " terms, doc_id, deadline, created, updated) VALUES (?,?,?,?,?,'draft',?,?,?,?,?)",
            (deal_id, user_id, fields.get("deal_type", "split")[:40],
             fields.get("title", "Untitled deal")[:200],
             fields.get("counterparty", "")[:120], fields.get("terms", "")[:600],
             fields.get("doc_id"), fields.get("deadline", "")[:10], now, now))
    return deal_id


def update_deal(user_id, deal_id, fields):
    allowed = ("status", "terms", "deadline", "doc_id", "counterparty")
    sets, vals = [], []
    for key in allowed:
        if key in fields:
            sets.append("%s = ?" % key)
            vals.append(fields[key])
    if not sets:
        return False
    sets.append("updated = ?")
    vals.extend([_now(), deal_id, user_id])
    with get_db() as db:
        cur = db.execute("UPDATE deals SET %s WHERE id = ? AND user_id = ?"
                         % ", ".join(sets), vals)
    return cur.rowcount > 0


def list_deals(user_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM deals WHERE user_id = ? ORDER BY updated DESC",
                          (user_id,)).fetchall()
    return [dict(r) for r in rows]

# --- Sync clearance packs --------------------------------------------------------

def create_sync_pack(user_id, slug, fields):
    pack_id = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO sync_packs (id, user_id, slug, title, artist_name, bpm, song_key,"
            " moods, master_status, publishing_status, ownership_note, contact_email,"
            " main_url, instrumental_url, clean_url, created, updated)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pack_id, user_id, slug, fields.get("title", "Untitled")[:150],
             fields.get("artist_name", "")[:120], fields.get("bpm", "")[:10],
             fields.get("song_key", "")[:20], fields.get("moods", "")[:200],
             fields.get("master_status", "unconfirmed")[:20],
             fields.get("publishing_status", "unconfirmed")[:20],
             fields.get("ownership_note", "")[:400],
             fields.get("contact_email", "")[:120],
             fields.get("main_url", ""), fields.get("instrumental_url", ""),
             fields.get("clean_url", ""), now, now))
    return pack_id


def update_sync_pack(user_id, pack_id, fields):
    allowed = ("status", "master_status", "publishing_status", "ownership_note")
    sets, vals = [], []
    for key in allowed:
        if key in fields:
            sets.append("%s = ?" % key)
            vals.append(fields[key])
    if not sets:
        return False
    sets.append("updated = ?")
    vals.extend([_now(), pack_id, user_id])
    with get_db() as db:
        cur = db.execute("UPDATE sync_packs SET %s WHERE id = ? AND user_id = ?"
                         % ", ".join(sets), vals)
    return cur.rowcount > 0


def list_sync_packs(user_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM sync_packs WHERE user_id = ? ORDER BY updated DESC",
                          (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_sync_pack_by_slug(slug, count_view=False):
    with get_db() as db:
        row = db.execute("SELECT * FROM sync_packs WHERE slug = ?", (slug,)).fetchone()
        if row and count_view:
            db.execute("UPDATE sync_packs SET views = views + 1 WHERE slug = ?", (slug,))
    return dict(row) if row else None

# --- Artist Twin -----------------------------------------------------------------

def save_twin_settings(user_id, sources, tone, do_not_say):
    with get_db() as db:
        db.execute(
            "INSERT INTO twin_settings (user_id, sources, tone, do_not_say, updated)"
            " VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET"
            " sources=excluded.sources, tone=excluded.tone,"
            " do_not_say=excluded.do_not_say, updated=excluded.updated",
            (user_id, json.dumps(sources), tone, do_not_say[:400], _now()))


def get_twin_settings(user_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM twin_settings WHERE user_id = ?",
                         (user_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["sources"] = json.loads(d["sources"] or "[]")
    return d


def save_twin_generation(user_id, kind, output, sources_used):
    gen_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO twin_generations (id, user_id, kind, output, sources_used, created)"
            " VALUES (?,?,?,?,?,?)",
            (gen_id, user_id, kind, output[:2000], sources_used[:200], _now()))
    return gen_id


def list_twin_generations(user_id, limit=20):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM twin_generations WHERE user_id = ? ORDER BY created DESC LIMIT ?",
            (user_id, limit)).fetchall()
    return [dict(r) for r in rows]

# --- Revenue OS expenses ---------------------------------------------------------

def add_expense(user_id, category, description, amount, spend_date=""):
    exp_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO revenue_expenses (id, user_id, category, description, amount,"
            " spend_date, created) VALUES (?,?,?,?,?,?,?)",
            (exp_id, user_id, category[:40], description[:200], float(amount),
             spend_date[:10], _now()))
    return exp_id


def list_expenses(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM revenue_expenses WHERE user_id = ?"
            " ORDER BY spend_date DESC, created DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_expense(user_id, exp_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM revenue_expenses WHERE id = ? AND user_id = ?",
                         (exp_id, user_id))
    return cur.rowcount > 0

# --- Spotify pre-saves -----------------------------------------------------------

def add_spotify_presave(campaign_id, spotify_user_id, email, refresh_token_enc):
    """Returns the presave id, or None if this fan already pre-saved.
    A repeat authorization refreshes the stored token and re-arms delivery
    (unless already completed) — fans re-consenting is a fix, not a no-op."""
    presave_id = uuid.uuid4().hex
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO spotify_presaves (id, campaign_id, spotify_user_id, email,"
                " refresh_token_enc, created) VALUES (?,?,?,?,?,?)",
                (presave_id, campaign_id, spotify_user_id, email,
                 refresh_token_enc, _now()))
    except sqlite3.IntegrityError:
        with get_db() as db:
            db.execute(
                "UPDATE spotify_presaves SET refresh_token_enc = ?, retry_count = 0,"
                " status = 'pending', error = '' "
                "WHERE campaign_id = ? AND spotify_user_id = ? AND status != 'completed'",
                (refresh_token_enc, campaign_id, spotify_user_id))
        return None
    return presave_id


def pending_spotify_presaves(campaign_id, limit=10):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM spotify_presaves WHERE campaign_id = ? AND status = 'pending'"
            " AND retry_count < 5 LIMIT ?", (campaign_id, limit)).fetchall()
    return [dict(r) for r in rows]


def resolve_spotify_presave(presave_id, status, error=""):
    with get_db() as db:
        if status == "completed":
            db.execute(
                "UPDATE spotify_presaves SET status='completed', completed_at=?,"
                " refresh_token_enc='' WHERE id = ?", (_now(), presave_id))
        else:
            db.execute(
                "UPDATE spotify_presaves SET retry_count = retry_count + 1, error = ?,"
                " status = CASE WHEN retry_count >= 4 THEN 'failed' ELSE 'pending' END"
                " WHERE id = ?", (error[:200], presave_id))


def count_spotify_presaves(campaign_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT status, COUNT(*) AS n FROM spotify_presaves WHERE campaign_id = ?"
            " GROUP BY status", (campaign_id,)).fetchall()
    return {r["status"]: r["n"] for r in rows}

# --- Hours desk -------------------------------------------------------------------
# Five tables behind one page: what you charge, what you worked, what you
# invoiced, what people booked, what collaborators submitted, and how the
# day is blocked out. Every figure the page shows is summed from these rows
# - nothing on the Hours desk is illustrative.

def _hours_clean_day(day):
    """Accept only YYYY-MM-DD; anything else becomes today, so a bad value
    can never land a row on a date that does not exist."""
    day = (day or "").strip()[:10]
    try:
        datetime.strptime(day, "%Y-%m-%d")
        return day
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def set_hours_rate(user_id, service, rate, min_hours=0, bookable=False,
                   notes="", sort=0):
    """Upsert one line of the rate card."""
    service = (service or "").strip()[:60]
    if not service:
        return None
    now = _now()
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM hours_rates WHERE user_id = ? AND service = ?",
            (user_id, service)).fetchone()
        if row:
            db.execute(
                "UPDATE hours_rates SET rate = ?, min_hours = ?, bookable = ?,"
                " notes = ?, sort = ? WHERE id = ?",
                (max(0.0, float(rate or 0)), max(0.0, float(min_hours or 0)),
                 1 if bookable else 0, (notes or "")[:200], int(sort or 0),
                 row["id"]))
            return row["id"]
        rate_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO hours_rates (id, user_id, service, rate, min_hours,"
            " bookable, notes, sort, created) VALUES (?,?,?,?,?,?,?,?,?)",
            (rate_id, user_id, service, max(0.0, float(rate or 0)),
             max(0.0, float(min_hours or 0)), 1 if bookable else 0,
             (notes or "")[:200], int(sort or 0), now))
    return rate_id


def list_hours_rates(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM hours_rates WHERE user_id = ? ORDER BY sort, service",
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_hours_rate(user_id, rate_id):
    with get_db() as db:
        cur = db.execute(
            "DELETE FROM hours_rates WHERE id = ? AND user_id = ?",
            (rate_id, user_id))
    return cur.rowcount > 0


def add_hours_entry(user_id, day, project, client, service, hours, rate,
                    note=""):
    entry_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO hours_entries (id, user_id, day, project, client,"
            " service, hours, rate, note, billed, invoice_id, created)"
            " VALUES (?,?,?,?,?,?,?,?,?,0,NULL,?)",
            (entry_id, user_id, _hours_clean_day(day), (project or "")[:120],
             (client or "")[:120], (service or "")[:60],
             max(0.0, float(hours or 0)), max(0.0, float(rate or 0)),
             (note or "")[:300], _now()))
    return entry_id


def list_hours_entries(user_id, unbilled_only=False):
    sql = "SELECT * FROM hours_entries WHERE user_id = ?"
    if unbilled_only:
        sql += " AND billed = 0"
    sql += " ORDER BY day DESC, created DESC"
    with get_db() as db:
        rows = db.execute(sql, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_hours_entry(user_id, entry_id):
    """Only unbilled rows can go: deleting a line off an issued invoice
    would leave the invoice claiming hours that no longer exist."""
    with get_db() as db:
        cur = db.execute(
            "DELETE FROM hours_entries WHERE id = ? AND user_id = ? AND billed = 0",
            (entry_id, user_id))
    return cur.rowcount > 0


def create_hours_invoice(user_id, entry_ids, number, client="", project=""):
    """Mark the given unbilled entries billed and record the invoice. Totals
    come from the rows themselves, so the invoice can never disagree with
    the log it was built from. Returns the invoice dict, or None if none of
    the ids were billable."""
    if not entry_ids:
        return None
    now = _now()
    with get_db() as db:
        marks = ",".join("?" for _ in entry_ids)
        rows = db.execute(
            "SELECT * FROM hours_entries WHERE user_id = ? AND billed = 0"
            " AND id IN (%s)" % marks, tuple([user_id] + list(entry_ids))
        ).fetchall()
        if not rows:
            return None
        hours = round(sum(float(r["hours"]) for r in rows), 2)
        total = round(sum(float(r["hours"]) * float(r["rate"]) for r in rows), 2)
        invoice_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO hours_invoices (id, user_id, number, client, project,"
            " hours, total, status, issued, paid)"
            " VALUES (?,?,?,?,?,?,?,'sent',?,NULL)",
            (invoice_id, user_id, (number or "")[:40], (client or "")[:120],
             (project or "")[:120], hours, total, now))
        ids = [r["id"] for r in rows]
        db.execute(
            "UPDATE hours_entries SET billed = 1, invoice_id = ? WHERE id IN (%s)"
            % ",".join("?" for _ in ids), tuple([invoice_id] + ids))
        made = db.execute("SELECT * FROM hours_invoices WHERE id = ?",
                          (invoice_id,)).fetchone()
    return dict(made)


def list_hours_invoices(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM hours_invoices WHERE user_id = ?"
            " ORDER BY issued DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def set_hours_invoice_paid(user_id, invoice_id):
    with get_db() as db:
        cur = db.execute(
            "UPDATE hours_invoices SET status = 'paid', paid = ?"
            " WHERE id = ? AND user_id = ? AND status != 'paid'",
            (_now(), invoice_id, user_id))
    return cur.rowcount > 0


def add_hours_booking(user_id, service, who, contact, day, start_hour, hours,
                      rate, note=""):
    booking_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO hours_bookings (id, user_id, service, who, contact,"
            " day, start_hour, hours, rate, status, note, created)"
            " VALUES (?,?,?,?,?,?,?,?,?,'requested',?,?)",
            (booking_id, user_id, (service or "")[:60], (who or "")[:120],
             (contact or "")[:160], _hours_clean_day(day),
             max(0.0, min(23.5, float(start_hour or 0))),
             max(0.25, float(hours or 1)), max(0.0, float(rate or 0)),
             (note or "")[:300], _now()))
    return booking_id


def list_hours_bookings(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM hours_bookings WHERE user_id = ? ORDER BY "
            "CASE status WHEN 'requested' THEN 0 WHEN 'confirmed' THEN 1 "
            "ELSE 2 END, day, start_hour", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def set_hours_booking_status(user_id, booking_id, status):
    if status not in ("requested", "confirmed", "declined", "done"):
        return False
    with get_db() as db:
        cur = db.execute(
            "UPDATE hours_bookings SET status = ? WHERE id = ? AND user_id = ?",
            (status, booking_id, user_id))
    return cur.rowcount > 0


def add_hours_submission(owner_id, who, role, day, hours, rate, note=""):
    sub_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO hours_submissions (id, owner_id, who, role, day,"
            " hours, rate, note, status, decided, reason, created)"
            " VALUES (?,?,?,?,?,?,?,?,'pending',NULL,'',?)",
            (sub_id, owner_id, (who or "")[:120], (role or "")[:60],
             _hours_clean_day(day), max(0.0, float(hours or 0)),
             max(0.0, float(rate or 0)), (note or "")[:300], _now()))
    return sub_id


def list_hours_submissions(owner_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM hours_submissions WHERE owner_id = ? ORDER BY "
            "CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 "
            "ELSE 2 END, day DESC", (owner_id,)).fetchall()
    return [dict(r) for r in rows]


def decide_hours_submission(owner_id, sub_id, approve, reason=""):
    """Approve or reject, recording who decided and when. A rejection keeps
    its reason: an unexplained rejected timesheet is how disputes start."""
    status = "approved" if approve else "rejected"
    with get_db() as db:
        cur = db.execute(
            "UPDATE hours_submissions SET status = ?, decided = ?, reason = ?"
            " WHERE id = ? AND owner_id = ? AND status = 'pending'",
            (status, _now(), (reason or "")[:300], sub_id, owner_id))
    return cur.rowcount > 0


def add_hours_block(user_id, day, start_hour, hours, label, kind="work"):
    block_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO hours_blocks (id, user_id, day, start_hour, hours,"
            " label, kind, done, created) VALUES (?,?,?,?,?,?,?,0,?)",
            (block_id, user_id, _hours_clean_day(day),
             max(0.0, min(23.5, float(start_hour or 0))),
             max(0.25, float(hours or 1)), (label or "")[:120],
             (kind or "work")[:20], _now()))
    return block_id


def list_hours_blocks(user_id, day=None):
    sql = "SELECT * FROM hours_blocks WHERE user_id = ?"
    args = [user_id]
    if day:
        sql += " AND day = ?"
        args.append(_hours_clean_day(day))
    sql += " ORDER BY day, start_hour"
    with get_db() as db:
        rows = db.execute(sql, tuple(args)).fetchall()
    return [dict(r) for r in rows]


def toggle_hours_block(user_id, block_id):
    with get_db() as db:
        cur = db.execute(
            "UPDATE hours_blocks SET done = 1 - done WHERE id = ? AND user_id = ?",
            (block_id, user_id))
    return cur.rowcount > 0


def delete_hours_block(user_id, block_id):
    with get_db() as db:
        cur = db.execute(
            "DELETE FROM hours_blocks WHERE id = ? AND user_id = ?",
            (block_id, user_id))
    return cur.rowcount > 0
