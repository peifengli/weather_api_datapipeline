import boto3
from botocore.exceptions import ClientError
import requests
import json
import time
import os

def get_secret():

    secret_name = "openweather_api_key"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        
        raise e

    secret = json.loads(get_secret_value_response['SecretString'])

    return secret['api_key']

def fetch_weather_data(api_key):
    # dt = int(time.time())
    lat = '40.7143'
    lon = '-74.006'
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}"
    response = requests.get(url).json()
    return response

def save_to_s3(bucket_name, data):
    s3 = boto3.client('s3')
    dt = str(int(time.time()))
    s3.put_object(Bucket=bucket_name, Key=dt, Body=json.dumps(data))

def main():
    bucket_name = "weatherdata1"
    
    api_key = get_secret()
    weather_data = fetch_weather_data(api_key)
    save_to_s3(bucket_name, weather_data)

if __name__ == "__main__":
    main()