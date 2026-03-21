import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def aws_s3(monkeypatch):
    """Mocked S3 using moto — no LocalStack needed for unit-level integration tests."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="weatherdata-raw-test")
        client.create_bucket(Bucket="weatherdata-processed-test")
        yield client


@pytest.fixture
def aws_secrets(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with mock_aws():
        client = boto3.client("secretsmanager", region_name="us-east-1")
        client.create_secret(
            Name="weather-api-key",
            SecretString='{"OPENWEATHERMAP_API_KEY": "test-key-123"}',
        )
        yield client
