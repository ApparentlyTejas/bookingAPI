-- Applied manually (not via SQLAlchemy create_all()):
--   docker compose exec db psql -U app -d bookingapi -f /db/001_schema.sql

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS resources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    resource_id INTEGER NOT NULL REFERENCES resources(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bookings_resource_id ON bookings(resource_id);

-- ---------------------------------------------------------------------------
-- VERIFICATION QUERY (step 3): run manually after a load test against the
-- naive check-then-insert endpoint to find overlapping bookings on the same
-- resource. Any rows returned = the race condition landed overlapping data
-- in the DB. Paste this into `docker compose exec db psql -U app -d bookingapi`:
--
-- SELECT a.id AS booking_a, b.id AS booking_b, a.resource_id,
--        a.start_time, a.end_time, b.start_time, b.end_time
-- FROM bookings a
-- JOIN bookings b ON a.resource_id = b.resource_id AND a.id < b.id
-- WHERE a.start_time < b.end_time AND b.start_time < a.end_time;
