-- Applied manually (not via SQLAlchemy create_all()):
--   docker compose exec db psql -U app -d bookingapi -f /db/007_resource_metadata.sql
--
-- Room metadata: capacity (headcount) and amenities (native Postgres text
-- array — this project is Postgres-only by design already, given the
-- exclusion constraint, so there's no portability reason to serialize this
-- as JSON/CSV instead).

ALTER TABLE resources ADD COLUMN capacity INTEGER;
ALTER TABLE resources ADD COLUMN amenities TEXT[] NOT NULL DEFAULT '{}';
