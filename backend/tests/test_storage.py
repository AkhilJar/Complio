import uuid

from config import settings
from storage.client import download_file, ensure_bucket, s3, upload_file


#integration test: needs the minio container up, which compose guarantees
#before the api starts. proves the container, the credentials and the
#boto3 wiring all line up — not that any particular file type works.
def test_bucket_upload_download_round_trip(tmp_path):
    bucket = ensure_bucket()
    assert bucket == settings.minio_bucket

    #unique key so reruns never collide with leftovers in the volume
    key = f"test/{uuid.uuid4()}.txt"
    contents = "minio round-trip works"

    source = tmp_path / "source.txt"
    source.write_text(contents)

    try:
        upload_file(str(source), key)

        listed = s3.list_objects_v2(Bucket=bucket, Prefix=key).get("Contents", [])
        assert [o["Key"] for o in listed] == [key]

        target = tmp_path / "target.txt"
        download_file(key, str(target))
        assert target.read_text() == contents
    finally:
        #leave the bucket as we found it so the test is repeatable
        s3.delete_object(Bucket=bucket, Key=key)


#ensure_bucket runs on an existing bucket without raising
def test_ensure_bucket_is_idempotent():
    assert ensure_bucket() == ensure_bucket()
