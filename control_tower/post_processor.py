import json
import requests


class PostProcessor:

    def __init__(self, args, errors, galloper):
        self.errors = errors
        self.galloper = galloper
        self.args = args
        self.config_file = None

    def results_post_processing(self):
        aggregated_errors = self.aggregate_errors(self.errors)

        if self.galloper:
            with open("/tmp/config.yaml", "r") as f:
                self.config_file = f.read()
            data = {'arguments': json.dumps(self.args), 'config_file': json.dumps(self.config_file),
                    'aggregated_errors': json.dumps(aggregated_errors)}
            headers = {'content-type': 'application/json'}
            r = requests.post(self.galloper, json=data, headers=headers)
            print(r.text)
        else:
            try:
                from perfreporter.post_processor import PostProcessor
            except Exception as e:
                print(e)
            post_processor = PostProcessor(self.args, aggregated_errors)
            post_processor.post_processing()

    @staticmethod
    def aggregate_errors(test_errors):
        aggregated_errors = {}
        for errors in test_errors:
            for err in errors:
                if err not in aggregated_errors:
                    aggregated_errors[err] = errors[err]
                else:
                    aggregated_errors[err]['Error count'] = int(aggregated_errors[err]['Error count']) \
                                                            + int(errors[err]['Error count'])

        return aggregated_errors
