import os
import zipfile
import requests


def process_csv(galloper_url, token, project_id, artifact, bucket, csv_path, lg_count):
    download_artifact(galloper_url, project_id, token, bucket, artifact)
    csv_files = split_csv(csv_path, lg_count)
    csv_array = upload_csv(galloper_url, token, project_id, csv_files, bucket, csv_path)
    return csv_array


def download_artifact(galloper_url, project_id, token, bucket, artifact):
    endpoint = f'/api/v1/artifacts/{project_id}/{bucket}/{artifact}'
    headers = {'Authorization': f'bearer {token}'}
    r = requests.get(f'{galloper_url}/{endpoint}', allow_redirects=True, headers=headers)
    with open("/tmp/file_data.zip", 'wb') as file_data:
        file_data.write(r.content)
    os.mkdir("/tmp/file_data")
    with zipfile.ZipFile("/tmp/file_data.zip", 'r') as zip_ref:
        zip_ref.extractall("/tmp/file_data")


def split_csv(csv_path, lg_count):
    os.mkdir("/tmp/scv_files")
    with open(f"/tmp/file_data/{csv_path}", "r") as csv:
        csv_lines = csv.readlines()
    lines_per_generator = int(len(csv_lines)/lg_count)
    csv_name = csv_path.split("/")[-1].split(".csv")[0]
    csv_suffix = 1
    csv_array = []
    _tmp = []
    for each in csv_lines:
        if len(_tmp) != lines_per_generator:
            _tmp.append(each)
        else:
            with open(f"/tmp/scv_files/{csv_name}_{csv_suffix}.csv", "w") as f:
                for line in _tmp:
                    f.write(f"{line}")
            csv_array.append(f"/tmp/scv_files/{csv_name}_{csv_suffix}.csv")
            _tmp = []
            _tmp.append(each)
            csv_suffix += 1

    if len(csv_array) < lg_count and _tmp:
        with open(f"/tmp/scv_files/{csv_name}_{csv_suffix}.csv", "w") as f:
            for line in _tmp:
                f.write(f"{line}")
        csv_array.append(f"/tmp/scv_files/{csv_name}_{csv_suffix}.csv")
    return csv_array


def upload_csv(galloper_url, token, project_id, csv_files, bucket, csv_path):
    csv_array = []
    headers = {'Authorization': f'bearer {token}'}
    upload_url = f'{galloper_url}/api/v1/artifacts/{project_id}/{bucket}/file'
    for each in csv_files:
        csv_name = each.replace("/tmp/scv_files/", "")
        files = {'file': open(each, 'rb')}
        requests.post(upload_url, allow_redirects=True, files=files, headers=headers)
        csv_array.append({f"{bucket}/{csv_name}": f"/mnt/jmeter/{csv_path}"})
    return csv_array


def delete_csv(galloper_url, token, project_id, artifact):
    url = f'{galloper_url}/api/v1/artifacts/{project_id}/tests'
    headers = {'Authorization': f'bearer {token}'} if token else {}
    requests.delete(f'{url}/file?fname[]={artifact}', headers=headers)
