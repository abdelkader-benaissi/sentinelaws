output "quarantine_security_group_id" { value = aws_security_group.quarantine.id }
output "incident_table_name" { value = aws_dynamodb_table.incidents.name }
output "quarantine_function_name" { value = aws_lambda_function.quarantine.function_name }
output "waf_block_function_name" { value = aws_lambda_function.waf_block.function_name }

