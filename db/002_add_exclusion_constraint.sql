-- Applied manually (not via SQLAlchemy create_all()):
--   docker compose exec db psql -U app -d bookingapi -f /db/002_add_exclusion_constraint.sql
--
-- Fix attempt 2: instead of locking the resource row app-side before
-- every insert (fix attempt 1), let Postgres reject overlapping
-- bookings at the database level. An EXCLUDE constraint on
-- (resource_id, tsrange(start_time, end_time)) makes any two rows with the
-- same resource_id and overlapping time ranges mutually exclusive — the
-- second INSERT in a race fails with a constraint violation instead of
-- succeeding. Unlike the FOR UPDATE fix, this only blocks genuinely
-- overlapping bookings; non-overlapping bookings on the same resource can
-- commit concurrently.

-- Required for a GiST index to support equality (=) on a plain scalar
-- column (resource_id) alongside the range overlap (&&) operator.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- tstzrange, not tsrange: start_time/end_time are TIMESTAMPTZ (see
-- 001_schema.sql). tsrange is for timestamp-without-timezone columns and
-- would fail to compile against these.
ALTER TABLE bookings
    ADD CONSTRAINT bookings_no_overlap
    EXCLUDE USING gist (
        resource_id WITH =,
        tstzrange(start_time, end_time) WITH &&
    );
