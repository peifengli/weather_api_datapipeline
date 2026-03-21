import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # OpenWeatherMap
    openweather_api_key: str = field(default_factory=lambda: os.getenv("OPENWEATHERMAP_API_KEY", ""))
    weather_units: str = field(default_factory=lambda: os.getenv("WEATHER_UNITS", "imperial"))

    # AWS
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_DEFAULT_REGION", "us-east-1"))

    # S3
    s3_raw_bucket: str = field(default_factory=lambda: os.getenv("S3_RAW_BUCKET", "weatherdata-raw"))
    s3_processed_bucket: str = field(default_factory=lambda: os.getenv("S3_PROCESSED_BUCKET", "weatherdata-processed"))
    s3_athena_results_bucket: str = field(default_factory=lambda: os.getenv("S3_ATHENA_RESULTS_BUCKET", "weatherdata-athena-results"))

    # Athena
    athena_database: str = field(default_factory=lambda: os.getenv("ATHENA_DATABASE", "weather_db"))
    athena_workgroup: str = field(default_factory=lambda: os.getenv("ATHENA_WORKGROUP", "primary"))

    # Environment
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "local"))
    localstack_endpoint: str = field(default_factory=lambda: os.getenv("LOCALSTACK_ENDPOINT_URL", "http://localstack:4566"))

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @property
    def aws_endpoint_url(self) -> str | None:
        return self.localstack_endpoint if self.is_local else None
