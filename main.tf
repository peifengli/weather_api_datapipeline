provider "aws" {
  region = "us-east-1"
}

resource "aws_secretsmanager_secret" "openweather_api_key" {
  name = "openweather_api_key"
}

# Create S3 bucket
resource "aws_s3_bucket" "weatherdata1" {
  bucket = "weatherdata1"
}

# Create S3 bucket for script
resource "aws_s3_bucket" "gluescriptbucket1" {
  bucket = "gluescriptbucket1"
}

# Upload script for glue 
resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.gluescriptbucket1.bucket
  key = "weather-api.py"
  # Local path to Python script
  source = "/Users/bryton/terraform/openweather-api-project/weather-api.py" 
}

# IAM role for AWS glue
resource "aws_iam_role" "glue_schedule_role" {
  name = "glue_schedule_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "glue.amazonaws.com"
        }
      }
    ]
  })
}

# Policy for aws glue job to access S3 and run schedule scripts
resource "aws_iam_policy" "glue_schedule_role_policy" {
  name = "glue_schedule_role_policy"
  description = "Policy for aws glue job to access S3 and run schedule scripts"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ],
        Resource = "*"
      },
      {
        Effect   = "Allow",
        Action   = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*"
      },
      {
        Effect   = "Allow",
        Action   = [
          "glue:StartJobRun",
          "glue:GetJobRun",
          "glue:GetJobRuns",
          "glue:BatchStopJobRun"
        ],
        Resource = "*"
      },
      {
        Effect   = "Allow",
        Action   = [
          "secretsmanager:GetSecretValue",
        ],
        Resource =   "arn:aws:secretsmanager:us-east-1:654654412570:secret:openweather_api_key-3wk9qs"# Replace with your secret ARN
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "glue_schedule_role_policy_attachment" {
  role = aws_iam_role.glue_schedule_role.name
  policy_arn = aws_iam_policy.glue_schedule_role_policy.arn
}



# Create AWS glue job
resource "aws_glue_job" "python_job" {
  name = "python_job"
  role_arn = aws_iam_role.glue_schedule_role.arn
  command {
    name = "glueetl"
    script_location = "s3://${aws_s3_bucket.gluescriptbucket1.bucket}/weather-api.py"
    python_version = "3"
  }
  max_retries = 1
  glue_version = "3.0"
  number_of_workers = 2
  worker_type = "G.1X"
}

# Schedule glue job to run every 10 minutes
resource "aws_glue_trigger" "every_10_minutes" {
  name       = "glue-job-every-10-minutes"
  type       = "SCHEDULED"
  schedule   = "cron(0/10 * * * ? *)"
  actions {
    job_name = aws_glue_job.python_job.name
  }
  start_on_creation = true
}

# Create IAM roles and policies for glue and athena
resource "aws_iam_role" "glue_catalog_role" {
  name = "glue_catalog_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "glue.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "glue_catalog_policy" {
  name = "glue_catalog_policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "s3:ListBucket",
          "s3:GetObject"
        ],
        Effect = "Allow",
        Resource = "*"
      },
      {
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetPartitions",
          "glue:CreateTable",
          "glue:UpdateTable",
          "glue:DeleteTable",
          "glue:CreateDatabase",
          "glue:UpdateDatabase",
          "glue:DeleteDatabase"
        ],
        Effect = "Allow",
        Resource = "*"
      },
      {
        Action = "logs:*",
        Effect = "Allow",
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "glue_catalog_role_attachment" {
  role = aws_iam_role.glue_catalog_role.name
  policy_arn = aws_iam_policy.glue_catalog_policy.arn
}

# Create AWS glue database
resource "aws_glue_catalog_database" "weather_catalog_database" {
  name = "weather_catalog_database"
}

# Create AWS glue table
resource "aws_glue_catalog_table" "weather_catalog_table" {
  name = "weather_catalog_table"
  database_name = aws_glue_catalog_database.weather_catalog_database.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classication = "json"
    "json.path" = "$"
  }

  storage_descriptor {
    columns {
      name = "coord"
      type = "struct<lon:double,lat:double>"
    }

    columns {
      name = "weather"
      type = "array<struct<id:int,main:string,description:string,icon:string>>"
    }

    columns {
      name = "base"
      type = "string"
    }

    columns {
      name = "main"
      type = "struct<temp:double,feels_like:double,temp_min:double,temp_max:double,pressure:int,humidity:int,sea_level:int,grnd_level:int>"
    }

    columns {
      name = "visibility"
      type = "int"
    }

    columns {
      name = "wind"
      type = "struct<speed:double,deg:int,gust:double>"
    }

    columns {
      name = "rain"
      type = "struct<1h:double>"
    }

    columns {
      name = "clouds"
      type = "struct<all:int>"
    }

    columns {
      name = "dt"
      type = "bigint"
    }

    columns {
      name = "sys"
      type = "struct<type:int,id:int,country:string,sunrise:bigint,sunset:bigint>"
    }

    columns {
      name = "timezone"
      type = "int"
    }

    columns {
      name = "id"
      type = "int"
    }

    columns {
      name = "name"
      type = "string"
    }

    columns {
      name = "cod"
      type = "int"
    }

    location = "s3://${aws_s3_bucket.weatherdata1.bucket}"

    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                 = "glue"
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    compressed = false
    number_of_buckets = -1
  }
}

# Create an athena work group
resource "aws_athena_workgroup" "weather_athena_workgroup" {
  name = "weather_athena_workgroup"

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.weatherdata1.bucket}"
    }
  }
}

# Create an athena named query 
resource "aws_athena_named_query" "weather_query" {
  name = "weather_query"
  database = aws_glue_catalog_database.weather_catalog_database.name
  query = <<EOF
SELECT * FROM weather_catalog_table LIMIT 10;
EOF
  description = "A simple query to fetch data from the weather table"
  workgroup   = aws_athena_workgroup.weather_athena_workgroup.name
} 


output "openweather" {
  value = aws_s3_bucket.weatherdata1.bucket
}