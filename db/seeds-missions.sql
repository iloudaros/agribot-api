INSERT INTO missions (
    id,
    commander_id,
    field_id,
    mission_type,
    status,
    start_time,
    end_time,
    mission_date
)
VALUES
    (
        'pc1-demo-inspection-001',
        2,
        1,
        'pc1_inspection',
        'complete',
        TIMESTAMP '2025-05-16 09:45:00',
        TIMESTAMP '2025-05-16 09:58:00',
        TIMESTAMP '2025-05-16 09:45:00'
    ),
    (
        'pc2-demo-spraying-001',
        3,
        1,
        'pc2_spraying',
        'complete',
        TIMESTAMP '2025-05-16 10:27:42',
        TIMESTAMP '2025-05-16 10:33:59',
        TIMESTAMP '2025-05-16 10:27:42'
    ),
    (
        'pc3-demo-inspection-001',
        3,
        2,
        'pc3_inspection',
        'complete',
        TIMESTAMP '2025-05-13 12:14:08',
        TIMESTAMP '2025-05-13 12:14:28',
        TIMESTAMP '2025-05-13 12:14:08'
    );

INSERT INTO pc1_weed (
    inspection_id,
    name,
    image,
    confidence,
    weed_loc,
    is_sprayed,
    spray_time
)
VALUES
    (
        'pc1-demo-inspection-001',
        'weed',
        'minio://agribot-mission-images/pc1/weeds_01.png',
        0.70,
        ST_SetSRID(ST_MakePoint(23.373180, 38.291420), 4326),
        false,
        NULL
    ),
    (
        'pc1-demo-inspection-001',
        'weed',
        'minio://agribot-mission-images/pc1/weeds_02.png',
        0.92,
        ST_SetSRID(ST_MakePoint(23.372988, 38.291565), 4326),
        true,
        TIMESTAMP '2025-05-16 10:10:00'
    );

INSERT INTO pc2_spraying_metadata (
    id,
    max_lat,
    min_lat,
    max_long,
    min_long,
    area_analyzed,
    average_density,
    crop_weed_correlation,
    weed_liquid_correlation
)
VALUES
    (
        'pc2-demo-spraying-001',
        46.96215985170065,
        46.95933422323656,
        7.140545172632977,
        7.136902175210454,
        0.2337060009465376,
        2521471.9731952,
        0.62,
        0.74
    );

INSERT INTO pc2_spraying_mission (id, properties)
VALUES
    (
        'pc2-demo-spraying-001',
        '{
            "start_time_ms": 1747408062392,
            "end_time_ms": 1747408439367,
            "robot_id": "erxbot-1910",
            "field_owner": "T013",
            "field_name": "26",
            "travelled_distance_m": 418.86887,
            "covered_area_m2": 2574.026,
            "sprayed_fluid_l": 5.3678803,
            "context_eppo": "DAUCA",
            "target_eppo": "WEED",
            "is_selective": true,
            "target_fluid_surface_density_lpha": 200.0,
            "setpoint_pressure_bar": 3.0,
            "cultivation_method": "RIDGES",
            "erx_soft_version": "release/2025.04.15",
            "inference_model": "DAUCA/8"
        }'::jsonb
    );

INSERT INTO pc3_inspections (
    id,
    location,
    biomass,
    ndvi
)
VALUES
    (
        'pc3-demo-inspection-001',
        ST_SetSRID(ST_MakePoint(16.7983850, 41.1398829), 4326),
        603.197958145333,
        0.701093289426946
    );
