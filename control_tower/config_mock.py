

class Config(object):
    def __init__(self, container="getcarrier/perfmeter:latest",
                 execution_params={"cmd": "-n -t /mnt/jmeter/FloodIO.jmx "
                                          "-JVUSERS=10 -JDURATION=120 -JRAMP_UP=1 -Jtest_name=test"},
                 job_type="free_style", job_name="test", concurrency=1, groupid=None):
        self.container = container
        self.execution_params = execution_params
        self.job_type = job_type
        self.job_name = job_name
        self.concurrency = concurrency
        self.groupid = groupid

    def get_config(self):
        return dict(container=self.container,
                    execution_params=self.execution_params,
                    job_type=self.job_type,
                    job_name=self.job_name,
                    concurrency=self.concurrency,
                    groupid=self.groupid)

