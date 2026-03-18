-- Sync the sequences so the next auto-generated IDs start AFTER our seeded data
SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT MAX(id) FROM users));
SELECT setval(pg_get_serial_sequence('farms', 'id'), (SELECT MAX(id) FROM farms));
SELECT setval(pg_get_serial_sequence('fields', 'id'), (SELECT MAX(id) FROM fields));