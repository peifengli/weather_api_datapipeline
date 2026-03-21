output "fetch_job_name" { value = aws_glue_job.fetch_weather.name }
output "process_job_name" { value = aws_glue_job.process_weather.name }
output "catalog_database" { value = aws_glue_catalog_database.weather.name }
output "crawler_name" { value = aws_glue_crawler.weather.name }
