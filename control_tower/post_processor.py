from os import path
import json
import requests


class PostProcessor:

    def __init__(self, galloper_url, galloper_web_hook, bucket, prefix):
        self.galloper_url = galloper_url
        self.galloper_web_hook = galloper_web_hook
        self.bucket = bucket
        self.prefix = prefix
        self.config_file = '{}'

    def results_post_processing(self):

        if self.galloper_web_hook:
            if path.exists('/tmp/config.yaml'):
                with open("/tmp/config.yaml", "r") as f:
                    self.config_file = f.read()

            data = {'galloper_url': self.galloper_url, 'config_file': json.dumps(self.config_file),
                    'bucket': self.bucket, 'prefix': self.prefix}
            headers = {'content-type': 'application/json'}
            r = requests.post(self.galloper_web_hook, json=data, headers=headers)
            print(r.text)
        else:
            try:
                from perfreporter.post_processor import PostProcessor
            except Exception as e:
                print(e)
            post_processor = PostProcessor(self.config_file)
            post_processor.distributed_mode_post_processing(self.galloper_url, self.bucket, self.prefix)


