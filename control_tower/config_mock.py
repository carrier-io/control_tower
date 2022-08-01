

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
    def __init__(self, bulk_container, bulk_params, job_type, job_name, bulk_concurrency, channel=[],
                 bucket="", artifact="", save_reports=False, junit=False, quality_gate=False, deviation=0,
                 max_deviation=0, report_path="/tmp/reports", test_id='', jira=False, report_portal=False,
                 email=False, azure_devops=False, email_recipients=None, integrations={}):
        self.container = bulk_container
        self.execution_params = bulk_params
        self.job_name = job_name
        self.concurrency = bulk_concurrency
        self.job_type = job_type
        self.channel = channel
        self.bucket = bucket
        self.artifact = artifact
        self.save_reports = save_reports
        self.junit = junit
        self.quality_gate = quality_gate
        self.deviation = deviation
        self.max_deviation = max_deviation
        self.report_path = report_path
        self.test_id = test_id
        self.jira = jira
        self.report_portal = report_portal
        self.email = email
        self.azure_devops = azure_devops
        self.email_recipients = email_recipients
        self.integrations = integrations

    def get_config(self):
        return dict(container=self.container,
                    execution_params=self.execution_params,
                    job_type=self.job_type,
                    job_name=self.job_name,
                    concurrency=self.concurrency,
                    channel=self.channel,
                    bucket=self.bucket,
                    artifact=self.artifact,
                    save_reports=self.save_reports,
                    junit=self.junit,
                    quality_gate=self.quality_gate,
                    deviation=self.deviation,
                    max_deviation=self.max_deviation,
                    report_path=self.report_path,
                    test_id=self.test_id,
                    jira=self.jira,
                    report_portal=self.report_portal,
                    email=self.email,
                    email_recipients=self.email_recipients,
                    integrations=self.integrations,
                    azure_devops=self.azure_devops)
