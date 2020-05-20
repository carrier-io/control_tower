# Control Tower
[![FOSSA Status](https://app.fossa.io/api/projects/git%2Bgithub.com%2Fcarrier-io%2Fcontrol_tower.svg?type=shield)](https://app.fossa.io/projects/git%2Bgithub.com%2Fcarrier-io%2Fcontrol_tower?ref=badge_shield)

_Executor for distributing jobs. Suppose to be used in CI jobs_

### Configuration
Configuration options through environment variables are:
`REDIS_HOST` - Host where redis is installed 

`REDIS_PORT` - Port for redis (default: 6379)

`REDIS_USER` - User to authenticate to redis (default is empty string) 

`REDIS_PASSWORD` -  Password for redis (default is password)

`REDIS_DB` - DB for tasks. could be helpful in multi-tenancy (default is 1)

### Execution parameters
`-c` - Name of container to run the job e.g. getcarrier/dusty:latest

`-e` - Execution params for jobs e.g. 
```
       {
         'host': 'localhost',
         'port': '443', 
         'protocol': 'https'
         'project_name': 'MY_PET',
         'environment':'stag',
         'test_type': 'basic'
       }
```
`-t` - Type of a job: e.g. sast, dast, perf-jmeter, perf-ui

`-n` - Name of a job (e.g. unique job ID, like %JOBNAME%_%JOBID%)

`-q` - Number of parallel workers to run the job

### Example:
```
docker run -t --rm \
       -e REDIS_HOST=localhost getcarrier/control_tower:latest \
       -c getcarrier/dast:latest \
       -e '{"host": "localhost", \
            "port":443, "protocol":"https", \
             "project_name":"TEST_PROJ", \
             "environment":"stag","test_type": "basic"} \
       -t dast -n supertestjob -q 1
```

### Example for observer

```
docker run -t --rm \
       -e REDIS_HOST=192.168.0.107 \
       -e OAToken="auth token here" \
       getcarrier/control_tower:latest \
       -c getcarrier/observer:latest \
       -e '{ "cmd": "-f data.zip -sc /tmp/data/webmail.side -r html -fp 100 -si 400 -tl 500", "REMOTE_URL": "localhost:4444", "LISTENER_URL": "localhost:9999","GALLOPER_URL": "http://localhost/api/v1", "GALLOPER_PROJECT_ID": "1"}' \
       -r 1 -t observer -q 1 -n web_perf
```

## License
[![FOSSA Status](https://app.fossa.io/api/projects/git%2Bgithub.com%2Fcarrier-io%2Fcontrol_tower.svg?type=large)](https://app.fossa.io/projects/git%2Bgithub.com%2Fcarrier-io%2Fcontrol_tower?ref=badge_large)