DROP TABLE IF EXISTS alarm_event_history;
DROP TABLE IF EXISTS maintenance_history;
DROP TABLE IF EXISTS quality_metrics;
DROP TABLE IF EXISTS process_status;
DROP TABLE IF EXISTS equipment_master;

CREATE TABLE equipment_master (
    equipment_id VARCHAR(50) PRIMARY KEY,
    line_id VARCHAR(50),
    process_name VARCHAR(100),
    equipment_type VARCHAR(100),
    location VARCHAR(100),
    criticality VARCHAR(20),
    owner_team VARCHAR(100)
);

CREATE TABLE process_status (
    status_id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    equipment_id VARCHAR(50),
    temperature NUMERIC(6,2),
    pressure NUMERIC(8,2),
    vacuum_level NUMERIC(8,3),
    speed NUMERIC(8,2),
    status VARCHAR(50)
);

CREATE TABLE quality_metrics (
    metric_id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    line_id VARCHAR(50),
    defect_rate NUMERIC(6,3),
    yield_rate NUMERIC(6,3),
    inspection_result VARCHAR(50),
    abnormal_flag BOOLEAN
);

CREATE TABLE maintenance_history (
    maintenance_id SERIAL PRIMARY KEY,
    maintenance_date DATE,
    equipment_id VARCHAR(50),
    maintenance_type VARCHAR(100),
    part_replaced VARCHAR(100),
    technician_note TEXT,
    downtime_min INTEGER
);

CREATE TABLE alarm_event_history (
    alarm_id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    line_id VARCHAR(50),
    equipment_id VARCHAR(50),
    alarm_code VARCHAR(50),
    severity VARCHAR(20),
    message TEXT,
    lot_id VARCHAR(50),
    operator_note TEXT
);