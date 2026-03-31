-- Sync the sequences so the next auto-generated IDs start AFTER our seeded data
SELECT setval(pg_get_serial_sequence('fields', 'id'), (SELECT MAX(id) FROM fields));