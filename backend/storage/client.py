import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from config import settings

#minio speaks the s3 api, so boto3 talks to it by pointing at a custom endpoint
#path-style addressing because the bucket-as-subdomain form does not resolve
#for a compose service name; region is required by signing but minio ignores it
s3 = boto3.client(
    "s3",
    endpoint_url=settings.minio_endpoint,
    aws_access_key_id=settings.minio_access_key,
    aws_secret_access_key=settings.minio_secret_key,
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    region_name="us-east-1",
)


#creating a bucket that already exists is an error, so check first
def ensure_bucket(bucket: str = None) -> str:
    bucket = bucket or settings.minio_bucket
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)
    return bucket


def upload_file(local_path: str, key: str, bucket: str = None) -> str:
    bucket = bucket or settings.minio_bucket
    s3.upload_file(local_path, bucket, key)
    return key


#upload_file goes through the filesystem; uploads that start life in memory
#(an api request body) must never be spilled to disk just to be re-read
def upload_bytes(data: bytes, key: str, content_type: str = None,
                 bucket: str = None) -> str:
    bucket = bucket or settings.minio_bucket
    extra = {"ContentType": content_type} if content_type else {}
    s3.put_object(Bucket=bucket, Key=key, Body=data, **extra)
    return key


#needed to roll back an upload when a later step fails, so a rejected
#request never leaves an object behind with no row pointing at it
def delete_object(key: str, bucket: str = None) -> None:
    bucket = bucket or settings.minio_bucket
    s3.delete_object(Bucket=bucket, Key=key)


def download_file(key: str, local_path: str, bucket: str = None) -> str:
    bucket = bucket or settings.minio_bucket
    s3.download_file(bucket, key, local_path)
    return local_path
