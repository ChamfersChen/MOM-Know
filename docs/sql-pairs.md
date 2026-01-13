查询创建人为fhj3的原材申请单记录 "SELECT id, application_number, create_by, create_time FROM raw_material_issuance_voucher WHERE create_by = 'fhj3' AND del_flag = '0';"

查询创建人为fhj3的每个申请单的 ID 和对应的申请数量 "SELECT r.id AS application_id, SUM(d.requested_quantity) AS total_requested_quantity FROM raw_material_issuance_voucher_detail d JOIN raw_material_issuance_voucher r ON d.material_issuance_voucher_id = r.id WHERE r.create_by = 'fhj3' GROUP BY r.id;"
