import argparse

from control_tower.run import start_and_track, str2bool, str2json


def test_demo():
    parser = argparse.ArgumentParser(description='Carrier Command Center')
    parser.add_argument('-c', '--container', action="append", type=str, default=[],
                        help="Name of container to run the job e.g. getcarrier/dusty:latest")
    parser.add_argument('-e', '--execution_params', action="append", type=str2json, default=[],
                        help="Execution params for jobs e.g. \n"
                             "{\n\t'host': 'localhost', \n\t'port':'443', \n\t'protocol':'https'"
                             ", \n\t'project_name':'MY_PET', \n\t'environment':'stag', \n\t"
                             "'test_type': 'basic'"
                             "\n} will be valid for dast container")
    parser.add_argument('-t', '--job_type', action="append", type=str, default=[],
                        help="Type of a job: e.g. sast, dast, perfmeter, perfgun, perf-ui")
    parser.add_argument('-n', '--job_name', type=str, default="",
                        help="Name of a job (e.g. unique job ID, like %JOBNAME%_%JOBID%)")
    parser.add_argument('-q', '--concurrency', action="append", type=int, default=[],
                        help="Number of parallel workers to run the job")
    parser.add_argument('-r', '--channel', action="append", default=[], type=int,
                        help="Number of parallel workers to run the job")
    parser.add_argument('-a', '--artifact', default="", type=str)
    parser.add_argument('-b', '--bucket', default="", type=str)
    parser.add_argument('-sr', '--save_reports', default=False, type=str2bool)
    parser.add_argument('-j', '--junit', default=False, type=str2bool)
    parser.add_argument('-qg', '--quality_gate', default=False, type=str2bool)
    parser.add_argument('-p', '--report_path', default="/tmp/reports", type=str)
    parser.add_argument('-d', '--deviation', default=0, type=float)
    parser.add_argument('-md', '--max_deviation', default=0, type=float)
    parser.add_argument('-tid', '--test_id', default="", type=str)

    args = parser.parse_args([
        "-c", "getcerrier/observer:latest",
        "-e",
        '{ "cmd": "-f data.zip -sc /tmp/data/webmail.side", "REMOTE_URL": "192.168.0.107:4444", "LISTENER_URL": "192.168.0.107:9999", "GALLOPER_PROJECT_ID": "1"}',
        "-r", "1",
        "-t", "observer",
        "-q", "1",
        "-n", "web_perf",
        "-j", "1",
        "-qg", "1"
    ])
    start_and_track(args)

