

class Config(object):
    def __init__(self):
        self.container = "busybox:latest"
        self.execution_params = {"cmd": "ping 8.8.8.8"}
        self.job_type = "free_style"
        self.job_name = "test"
        self.concurrency = 2
        self.groupid = None

    def set_group_id(self, id):
        self.groupid = id

    def get_config(self):
        return dict(container=self.container,
                    execution_params=self.execution_params,
                    job_type=self.job_type,
                    job_name=self.job_name,
                    concurrency=self.concurrency,
                    groupid=self.groupid)
