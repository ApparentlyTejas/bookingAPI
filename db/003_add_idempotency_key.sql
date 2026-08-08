-- Applied manually (not via SQLAlchemy create_all()):
--   docker compose exec db psql -U app -d bookingapi -f /db/003_add_idempotency_key.sql
--
-- Step 6: idempotency key on booking submission. A client resubmitting the
-- same booking (double-click, network retry) sends the same
-- Idempotency-Key each time; the UNIQUE constraint below means a second
-- INSERT with the same (user_id, idempotency_key) fails, and the app
-- catches that and returns the original booking instead of erroring or
-- creating a duplicate. NULL is allowed and not enforced for uniqueness
-- (Postgres treats NULLs as distinct in a UNIQUE constraint), so clients
-- that don't send a key keep working exactly as before.

ALTER TABLE bookings ADD COLUMN idempotency_key TEXT;

ALTER TABLE bookings
    ADD CONSTRAINT bookings_user_idempotency_key_unique
    UNIQUE (user_id, idempotency_key);
