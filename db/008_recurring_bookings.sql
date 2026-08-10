-- Applied manually (not via SQLAlchemy create_all()):
--   docker compose exec db psql -U app -d bookingapi -f /db/008_recurring_bookings.sql
--
-- Recurring bookings are just N ordinary rows in `bookings` that share a
-- series_id, created together by POST /bookings/recurring. Each occurrence
-- still goes through the exact same overlap check + EXCLUDE constraint as a
-- one-off booking — recurrence is purely a creation-time convenience and a
-- way to cancel-all-at-once later, it does not weaken the concurrency
-- guarantee or introduce a second code path for booking validity.
ALTER TABLE bookings ADD COLUMN series_id UUID;
CREATE INDEX IF NOT EXISTS idx_bookings_series_id ON bookings(series_id) WHERE series_id IS NOT NULL;
