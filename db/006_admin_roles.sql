-- Applied manually (not via SQLAlchemy create_all()):
--   docker compose exec db psql -U app -d bookingapi -f /db/006_admin_roles.sql
--
-- Role-based access: is_admin gates resource management (creating/deleting
-- rooms) and user role management. Defaults to FALSE for every existing and
-- future row — nobody is an admin until explicitly promoted (see the
-- bootstrap UPDATE in README.md's "Admin access" section, or via another
-- existing admin once one exists).

ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;
