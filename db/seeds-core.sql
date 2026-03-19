CREATE EXTENSION IF NOT EXISTS postgis;

TRUNCATE TABLE
    pc3_inspections,
    pc2_spraying_mission,
    pc2_spraying_metadata,
    pc1_weed,
    pc1_missions,      -- Added new PC1 status table
    missions,
    mission_types,
    field_ownerships,  -- Changed from farm_ownerships
    fields,            -- Farms table was removed
    users
RESTART IDENTITY CASCADE;

INSERT INTO users (id, username, password_hash, name, surname, role, is_active, created_at)
VALUES
    (
        1,
        'admin',
        '$2b$12$9g7VmVub67brQoYXRrb1nORFAD397U9V01OceO3KQgteFp3Kd3ki2',
        'System',
        'Admin',
        'admin',
        true,
        NOW()
    ),
    (
        2,
        'testuser',
        '$2b$12$9g7VmVub67brQoYXRrb1nORFAD397U9V01OceO3KQgteFp3Kd3ki2',
        'Demo',
        'Farmer',
        'farmer',
        true,
        NOW()
    ),
    (
        3,
        'perfect_farmer',
        '$2b$12$9g7VmVub67brQoYXRrb1nORFAD397U9V01OceO3KQgteFp3Kd3ki2',
        'Farmer',
        'Perfect',
        'farmer',
        true,
        NOW()
    ),
    (
        4,
        'servicebot',
        '$2b$12$9g7VmVub67brQoYXRrb1nORFAD397U9V01OceO3KQgteFp3Kd3ki2',
        'Field',
        'Operator',
        'service_provider',
        true,
        NOW()
    );

-- Merged Farm logic into Fields. Fields now hold the location_center
INSERT INTO fields (id, name, location_center, crop_name, boundary, created_at)
VALUES
    (
        1,
        'Field 26 - Demo Spraying',
        ST_SetSRID(ST_MakePoint(23.373150, 38.291430), 4326),
        'Potato',
        ST_GeomFromText(
            'POLYGON((
                7.136902 46.959334,
                7.140545 46.959334,
                7.140545 46.962160,
                7.136902 46.962160,
                7.136902 46.959334
            ))',
            4326
        ),
        NOW()
    ),
    (
        2,
        'Leafy Block A - Demo Monitoring',
        ST_SetSRID(ST_MakePoint(16.798420, 41.139860), 4326),
        'Leafy vegetables',
        ST_GeomFromText(
            'POLYGON((
                16.798350 41.139820,
                16.798520 41.139820,
                16.798520 41.139910,
                16.798350 41.139910,
                16.798350 41.139820
            ))',
            4326
        ),
        NOW()
    );

-- Replaced farm_ownerships with field_ownerships
INSERT INTO field_ownerships (field_id, user_id, ownership_percentage)
VALUES
    (1, 2, 60.00),
    (2, 2, 100.00),
    (1, 3, 40.00);

INSERT INTO mission_types (id, pilot_case, partner, description)
VALUES
    ('pc1_inspection_and_spraying', 'PC1', 'AUA', 'Inspection and spraying mission for weed identification'),
    ('pc2_spraying', 'PC2', 'Ecorobotix', 'Robotic spraying mission with application metadata'),
    ('pc3_inspection', 'PC3', 'POLIBA', 'Crop inspection mission with biomass and NDVI measurements');


-- Sync the sequences so the next auto-generated IDs start AFTER our seeded data
-- Note: 'farms' is removed from here since the table no longer exists
SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT MAX(id) FROM users));
SELECT setval(pg_get_serial_sequence('fields', 'id'), (SELECT MAX(id) FROM fields));
