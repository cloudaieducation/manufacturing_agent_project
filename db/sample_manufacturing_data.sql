INSERT INTO equipment_master 
(equipment_id, line_id, process_name, equipment_type, location, criticality, owner_team)
VALUES
('EQP-EV-03', 'LINE-07', 'Evaporation', 'Evaporation Chamber', 'Fab-A-3F', 'HIGH', 'Process Engineering Team'),
('EQP-CL-01', 'LINE-07', 'Cleaning', 'Cleaning Tool', 'Fab-A-2F', 'MEDIUM', 'Equipment Team'),
('EQP-IN-02', 'LINE-08', 'Inspection', 'Inspection Tool', 'Fab-B-1F', 'MEDIUM', 'Quality Team');

INSERT INTO process_status
(timestamp, equipment_id, temperature, pressure, vacuum_level, speed, status)
VALUES
('2026-05-15 09:00:00', 'EQP-EV-03', 72.50, 1.20, 0.003, 1200, 'NORMAL'),
('2026-05-15 09:30:00', 'EQP-EV-03', 85.20, 1.25, 0.004, 1200, 'WARNING'),
('2026-05-15 10:00:00', 'EQP-EV-03', 91.80, 1.30, 0.005, 1180, 'ALARM'),
('2026-05-15 10:30:00', 'EQP-EV-03', 89.40, 1.28, 0.005, 1185, 'ALARM');

INSERT INTO quality_metrics
(timestamp, line_id, defect_rate, yield_rate, inspection_result, abnormal_flag)
VALUES
('2026-05-15 09:00:00', 'LINE-07', 0.820, 98.500, 'PASS', false),
('2026-05-15 10:00:00', 'LINE-07', 1.750, 97.200, 'WARNING', true),
('2026-05-15 11:00:00', 'LINE-07', 2.300, 96.800, 'WARNING', true);

INSERT INTO maintenance_history
(maintenance_date, equipment_id, maintenance_type, part_replaced, technician_note, downtime_min)
VALUES
('2026-05-01', 'EQP-EV-03', 'Preventive Maintenance', 'Temperature Sensor', 'Temperature sensor calibration completed.', 45),
('2026-05-10', 'EQP-EV-03', 'Inspection', 'N/A', 'Vacuum line inspection completed.', 30);

INSERT INTO alarm_event_history
(timestamp, line_id, equipment_id, alarm_code, severity, message, lot_id, operator_note)
VALUES
('2026-05-15 09:35:00', 'LINE-07', 'EQP-EV-03', 'ALM-TEMP-402', 'HIGH', 'Temperature threshold exceeded.', 'LOT-20260515-001', 'Temperature rising faster than usual.'),
('2026-05-15 09:50:00', 'LINE-07', 'EQP-EV-03', 'ALM-TEMP-402', 'HIGH', 'Temperature threshold exceeded.', 'LOT-20260515-002', 'Repeated alarm after reset.'),
('2026-05-15 10:05:00', 'LINE-07', 'EQP-EV-03', 'ALM-TEMP-402', 'CRITICAL', 'Temperature exceeded safe operation range.', 'LOT-20260515-003', 'Process paused for safety check.'),
('2026-05-15 10:25:00', 'LINE-07', 'EQP-EV-03', 'ALM-TEMP-402', 'HIGH', 'Temperature threshold exceeded.', 'LOT-20260515-004', 'Alarm repeated within 1 hour.'),
('2026-05-15 10:45:00', 'LINE-07', 'EQP-EV-03', 'ALM-TEMP-402', 'HIGH', 'Temperature threshold exceeded.', 'LOT-20260515-005', 'Engineering review requested.');