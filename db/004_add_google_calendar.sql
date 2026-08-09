-- Applied manually (not via SQLAlchemy create_all()):
--   docker compose exec db psql -U app -d bookingapi -f /db/004_add_google_calendar.sql
--
-- Google Calendar sync (post-core-story addition): stores the OAuth refresh
-- token per user (obtained once via the /auth/google/connect consent flow)
-- and the resulting Google event ID per booking, so a synced booking's
-- calendar event is traceable back to this row if we ever add
-- cancel/update support.

ALTER TABLE users ADD COLUMN google_refresh_token TEXT;
ALTER TABLE bookings ADD COLUMN google_event_id TEXT;
