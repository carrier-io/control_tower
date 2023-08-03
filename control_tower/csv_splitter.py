import os
import zipfile
from typing import Optional

import requests
import shutil


def process_csv(galloper_url, token, project_id, artifact, bucket, csv_files, lg_count, s3_settings):
    download_artifact(galloper_url, project_id, token, bucket, artifact, s3_settings)
    files = split_csv(csv_files, lg_count)
    csv_array = upload_csv(galloper_url, token, project_id, files, bucket, csv_files, lg_count, s3_settings)
    return csv_array


def download_artifact(galloper_url, project_id, token, bucket, artifact, s3_settings):
    endpoint = f'/api/v1/artifacts/artifact/{project_id}/{bucket}/{artifact}'
    headers = {'Authorization': f'bearer {token}'}
    r = requests.get(f'{galloper_url}{endpoint}', params=s3_settings, allow_redirects=True, headers=headers)
    with open("/tmp/file_data.zip", 'wb') as file_data:
        file_data.write(r.content)
    try:
        os.mkdir("/tmp/file_data")
    except FileExistsError:
        shutil.rmtree("/tmp/file_data")
        os.mkdir("/tmp/file_data")
    with zipfile.ZipFile("/tmp/file_data.zip", 'r') as zip_ref:
        zip_ref.extractall("/tmp/file_data")


def split_csv(csv_files, lg_count):
    csv_dict = {}
    try:
        os.mkdir("/tmp/csv_files")
    except FileExistsError:
        shutil.rmtree("/tmp/csv_files")
        os.mkdir("/tmp/csv_files")
    for csv_path, header in csv_files.items():
        with open(f"/tmp/file_data/{csv_path}", "r") as csv:
            csv_lines = csv.readlines()

        if header:
            _header_line = csv_lines.pop(0)
        lines_per_generator = int(len(csv_lines)/lg_count)
        csv_name = csv_path.split("/")[-1].split(".csv")[0]
        csv_dict[f"{csv_name}.csv"] = []
        csv_suffix = 1

        _tmp = []
        for each in csv_lines:
            if len(_tmp) != lines_per_generator:
                _tmp.append(each)
            else:
                with open(f"/tmp/csv_files/{csv_name}_{csv_suffix}.csv", "w") as f:
                    if header:
                        f.write(f"{_header_line}")
                    for line in _tmp:
                        f.write(f"{line}")
                csv_dict[f"{csv_name}.csv"].append(f"/tmp/csv_files/{csv_name}_{csv_suffix}.csv")
                _tmp = []
                _tmp.append(each)
                csv_suffix += 1

        if len(csv_dict[f"{csv_name}.csv"]) < lg_count and _tmp:
            with open(f"/tmp/csv_files/{csv_name}_{csv_suffix}.csv", "w") as f:
                if header:
                    f.write(f"{_header_line}")
                for line in _tmp:
                    f.write(f"{line}")
            csv_dict[f"{csv_name}.csv"].append(f"/tmp/csv_files/{csv_name}_{csv_suffix}.csv")
    return csv_dict


def upload_csv(galloper_url, token, project_id, files, bucket, csv_files, lg_count, s3_settings: Optional[dict] = None):
    csv_array = []
    headers = {'Authorization': f'bearer {token}'}
    upload_url = f'{galloper_url}/api/v1/artifacts/artifacts/{project_id}/{bucket}'
    params = {} if not s3_settings else s3_settings

    for i in range(lg_count):
        csv_part = []
        for csv_path, header in csv_files.items():
            _csv_name = csv_path.split("/")[-1]
            _f = files[_csv_name].pop(0)
            csv_name = _f.replace("/tmp/csv_files/", "")
            _files = {'file': open(_f, 'rb')}

            requests.post(upload_url, allow_redirects=True, files=_files, headers=headers, params=params)
            csv_part.append({f"{bucket}/{csv_name}": f"/mnt/jmeter/{csv_path}"})
        csv_array.append(csv_part)
    return csv_array


def delete_csv(galloper_url, token, project_id, artifact):
    url = f'{galloper_url}/api/v1/artifacts/artifacts/{project_id}/tests'
    headers = {'Authorization': f'bearer {token}'} if token else {}
    requests.delete(f'{url}?fname[]={artifact}', headers=headers)
