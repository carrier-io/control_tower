

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


class BulkConfig(object):
    def __init__(self, bulk_container=["getcarrier/perfmeter:latest", "getcarrier/perfmeter:latest"],
                 bulk_params=[{"cmd": "-n -t /mnt/jmeter/FloodIO.jmx -JVUSERS=10 -JDURATION=120 -JRAMP_UP=1 -Jtest_name=test"},{"cmd": "-n -t /mnt/jmeter/FloodIO.jmx -JVUSERS=10 -JDURATION=120 -JRAMP_UP=1 -Jtest_name=test"}],
                 job_type=["free_style", "free_style"], job_name="test", bulk_concurrency=[1, 1], groupid=None, channels=[]):
        self.bulk_container = bulk_container
        self.bulk_params = bulk_params
        self.bulk_type = job_type
        self.job_name = job_name
        self.bulk_concurrency = bulk_concurrency
        self.concurrency = 0
        self.container = ''
        self.job_type = ''
        self.channels = channels
        self.groupid=groupid

    def get_config(self):
        return dict(bulk_container=self.bulk_container,
                    bulk_params=self.bulk_params,
                    job_type=self.job_type,
                    job_name=self.job_name,
                    bulk_concurrency=self.bulk_concurrency,
                    groupid=self.groupid,
                    channels=self.channels)
