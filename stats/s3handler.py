from urllib.parse import urlparse

import boto3
from django.conf import settings


class S3Handler:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )

    def get_image_bytes(self, s3_url):
        """Get image bytes from S3 URL"""
        parsed_url = urlparse(s3_url)
        bucket = parsed_url.netloc.split('.')[0]
        key = parsed_url.path.lstrip('/')

        response = self.s3_client.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()
