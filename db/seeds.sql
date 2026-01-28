-- AgriBot Data Lake - Dummy Data Seeds (CORRECTED)

TRUNCATE TABLE
    public.farmers, public.users, public.farms, public.crop_catalog,
    public.fields, public.devices, public.robots, public.missions,
    public.mission_images
RESTART IDENTITY CASCADE;

-- Let the database assign the ID
INSERT INTO farmers (first_name, last_name, email, created_at, updated_at)
VALUES ('John', 'Doe', 'john.doe@example.com', NOW(), NOW());

-- Let the database assign the ID. The hash here is for 'testpassword' from your previous step.
INSERT INTO users (username, password_hash, role, is_active, farmer_id, created_at, updated_at)
VALUES ('testuser', '$2b$12$ERzbpX3i4mlz9v0nZW0ZB.TszHNMS/UdCpcNrHbYWEyuAbP.DCp9C', 'farm_owner', true, 1, NOW(), NOW());

-- Populate Crop Catalog
INSERT INTO crop_catalog (eppo_code, common_name) VALUES ('DAUCA', 'Carrot'), ('ZEAMX', 'Maize');

-- Let the database assign the ID
INSERT INTO farms (farmer_id, name, created_at, updated_at)
VALUES (1, 'Doe Family Farm', NOW(), NOW());

-- Let the database assign the ID
INSERT INTO fields (farm_id, name, crop_id, polygon, created_at, updated_at)
VALUES (1, 'North Field', 1, ST_GeomFromText('POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))', 4326), NOW(), NOW());

-- Let the database assign the ID
INSERT INTO devices (type, name, serial_number, created_at, updated_at)
VALUES ('robot', 'Spraying Bot v1', 'AG-BOT-001', NOW(), NOW());

-- Let the database assign the ID
INSERT INTO robots (device_id, robot_name) VALUES (1, 'erxbot-agri-001');

\echo '✅ Dummy data has been inserted successfully (with database-managed IDs).'
