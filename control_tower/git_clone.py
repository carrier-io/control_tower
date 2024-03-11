import os
import io
import dulwich
from dulwich import porcelain
from dulwich.contrib.paramiko_vendor import ParamikoSSHVendor
import paramiko.transport
from paramiko.ssh_exception import SSHException
from paramiko.message import Message
import zipfile
from traceback import format_exc
import requests
from control_tower.run import logger


def _dulwich_repo_get_default_identity():
    try:
        return dulwich.repo.__original__get_default_identity()
    except:
        return ("Carrier User", "dusty@localhost")


def _paramiko_transport_verify_key(self, host_key, sig):
    key = self._key_info[self.host_key_type](Message(host_key))
    if key is None:
        raise SSHException('Unknown host key type')
    self.host_key = key


def _paramiko_client_SSHClient_auth(original_auth, forced_pkey):
    def __paramiko_client_SSHClient_auth(
            self, username, password, pkey, key_filenames, allow_agent, look_for_keys,
            gss_auth, gss_kex, gss_deleg_creds, gss_host, passphrase):
        return original_auth(
            self, username, password, forced_pkey, key_filenames, allow_agent, look_for_keys,
            gss_auth, gss_kex, gss_deleg_creds, gss_host, passphrase)
    return __paramiko_client_SSHClient_auth


def clone_repo(git_settings, test_build_id=None):
    logger.info("Cloning git repo ...")
    # Patch dulwich to work without valid UID/GID
    dulwich.repo.__original__get_default_identity = dulwich.repo._get_default_identity
    dulwich.repo._get_default_identity = _dulwich_repo_get_default_identity
    # Patch dulwich to use paramiko SSH client
    dulwich.client.get_ssh_vendor = ParamikoSSHVendor
    # Patch paramiko to skip key verification
    paramiko.transport.Transport._verify_key = _paramiko_transport_verify_key
    # Set USERNAME if needed
    try:
        getpass.getuser()
    except:  # pylint: disable=W0702
        os.environ["USERNAME"] = "git"

    try:
        os.mkdir("/tmp/git_dir")
    except:
        ...
    if test_build_id:
        os.mkdir(f"/tmp/git_dir/{test_build_id}")
        target = f"/tmp/git_dir/{test_build_id}"
    else:
        target = "/tmp/git_dir"
    # Get options
    source = git_settings.get("repo")
    branch = git_settings.get("repo_branch")
    if not branch:
        branch = "master"
    depth = None
    # Prepare auth
    auth_args = dict()
    if git_settings.get("repo_user"):
        auth_args["username"] = git_settings.get("repo_user")
    if git_settings.get("repo_pass"):
        auth_args["password"] = git_settings.get("repo_pass")
    if git_settings.get("repo_key"):
        key = git_settings.get("repo_key").replace("|", "\n")
        key_obj = io.StringIO(key)
        if "BEGIN RSA PRIVATE KEY" in key:
            pkey = paramiko.RSAKey.from_private_key(key_obj, auth_args.get("password", None))
        else:
            pkey = paramiko.Ed25519Key.from_private_key(key_obj, auth_args.get("password", None))

        # Patch paramiko to use our key
        paramiko.client.SSHClient._auth = _paramiko_client_SSHClient_auth(paramiko.client.SSHClient._auth, pkey)
    # Clone repository
    try:
        repository = porcelain.clone(
            source, target, checkout=False, depth=depth, **auth_args
        )
    except Exception as e:
        logger.error("GIT clone error ********************")
        logger.error(e)
        raise e
    try:
        branch = branch.encode("utf-8")
        repository[b"refs/heads/" + branch] = repository[b"refs/remotes/origin/" + branch]
        repository.refs.set_symbolic_ref(b"HEAD", b"refs/heads/" + branch)
        repository.reset_index(repository[b"HEAD"].tree)
    except KeyError:
        logger.error(f"The {branch} branch does not exist")
        raise Exception(f"The {branch} branch does not exist")


def zipdir(ziph, zip_path="/tmp/git_dir"):
    # ziph is zipfile handle
    for root, dirs, files in os.walk(zip_path):
        for f in files:
            ziph.write(os.path.join(root, f), os.path.join(root.replace(zip_path, ''), f))


def post_artifact(galloper_url, token, project_id, artifact, s3_settings, local_path=None):
    try:
        ziph = zipfile.ZipFile(f"/tmp/{artifact}", 'w', zipfile.ZIP_DEFLATED)
        if local_path:
            zipdir(ziph, zip_path=local_path)
        else:
            zipdir(ziph)
        ziph.close()
        files = {'file': open(f"/tmp/{artifact}", 'rb')}
        headers = {'Authorization': f'bearer {token}'} if token else {}
        upload_url = f'{galloper_url}/api/v1/artifacts/artifacts/{project_id}/tests'
        r = requests.post(upload_url, params=s3_settings, allow_redirects=True, files=files, headers=headers)
    except Exception:
        logger.error(format_exc())


def delete_artifact(galloper_url, token, project_id, artifact, s3_settings):
    url = f'{galloper_url}/api/v1/artifacts/artifacts/{project_id}/tests'
    headers = {'Authorization': f'bearer {token}'} if token else {}
    requests.delete(f'{url}?fname[]={artifact}', params=s3_settings, headers=headers)
