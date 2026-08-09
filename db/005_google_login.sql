-- Applied manually (not via SQLAlchemy create_all()):
--   docker compose exec db psql -U app -d bookingapi -f /db/005_google_login.sql
--
-- "Sign in with Google" support: an account created via Google OAuth has no
-- password at all (nothing to hash), so hashed_password must allow NULL.
-- app/routers/auth.py's login() explicitly checks for a NULL hash before
-- calling verify_password, rather than relying on it failing safe.

ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;
