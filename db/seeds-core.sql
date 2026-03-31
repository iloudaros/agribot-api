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

INSERT INTO users (id, email, password_hash, name, role, is_active, created_at)
VALUES
    (
        1,
        'admin@agribot.local',
        '$2b$12$9g7VmVub67brQoYXRrb1nORFAD397U9V01OceO3KQgteFp3Kd3ki2',
        'System Admin',
        'admin',
        true,
        NOW()
    ),
    (
        2,
        'testuser@agribot.local',
        '$2b$12$9g7VmVub67brQoYXRrb1nORFAD397U9V01OceO3KQgteFp3Kd3ki2',
        'Demo Farmer',
        'farmer',
        true,
        NOW()
    ),
    (
        3,
        'perfect_farmer@agribot.local',
        '$2b$12$9g7VmVub67brQoYXRrb1nORFAD397U9V01OceO3KQgteFp3Kd3ki2',
        'Perfect Farmer',
        'farmer',
        true,
        NOW()
    ),
    (
        4,
        'servicebot@agribot.local',
        '$2b$12$9g7VmVub67brQoYXRrb1nORFAD397U9V01OceO3KQgteFp3Kd3ki2',
        'Field Operator',
        'service_provider',
        true,
        NOW()
    );


INSERT INTO fields (id, name, crop_name, boundary, created_at)
VALUES
    (
        44,
        'Field 26 - Demo Spraying',
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
        45,
        'Leafy Block A - Demo Monitoring',
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
    (44, 2, 60.00),
    (45, 2, 100.00),
    (44, 3, 40.00);

INSERT INTO mission_types (id, pilot_case, partner, description)
VALUES
    ('pc1_inspection_and_spraying', 'PC1', 'AUA', 'Inspection and spraying mission for weed identification'),
    ('pc2_spraying', 'PC2', 'Ecorobotix', 'Robotic spraying mission with application metadata'),
    ('pc3_inspection', 'PC3', 'POLIBA', 'Crop inspection mission with biomass and NDVI measurements');


-- Sync the sequences so the next auto-generated IDs start AFTER our seeded data
-- Note: 'farms' is removed from here since the table no longer exists
SELECT setval(pg_get_serial_sequence('fields', 'id'), (SELECT MAX(id) FROM fields));
