import pytest
import requests_mock
from os import path
from control_tower.csv_splitter import process_csv

galloper_url = "http://example"
artifact = "test.zip"
token = "test"
project_id = 1
bucket = 'test'
# csv_files must be a dict: {csv_path: has_header}
csv_files = {"age.csv": True}
lg_count = 5


def test_split_csv():
    with requests_mock.Mocker() as mock:
        mock.get(f'{galloper_url}/api/v1/artifacts/artifact/{project_id}/{bucket}/{artifact}',
                 content=open('tests/test.zip', "rb").read(), status_code=200)
        mock.post(f'{galloper_url}/api/v1/artifacts/artifacts/{project_id}/{bucket}',
                  json={"status": "mocked"}, status_code=200)
        mock.post(f'{galloper_url}/api/v1/artifacts/artifacts/{project_id}/tests',
                  json={"status": "mocked"}, status_code=200)
        process_csv(galloper_url, token, project_id, artifact, bucket, csv_files, lg_count, s3_settings={})
        assert path.exists("/tmp/file_data/age.csv")
        for i in [1, 2, 3, 4, 5]:
            assert path.exists(f"/tmp/csv_files/age_{i}.csv")
            assert len(open(f"/tmp/csv_files/age_{i}.csv", "r").readlines()) == 20
