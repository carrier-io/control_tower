import json
import requests


class PostProcessor:

    def __init__(self, args, tests_results, galloper):
        self.tests_results = tests_results
        self.galloper = galloper
        self.args = args
        self.config_file = None

    def results_post_processing(self):
        aggregated_errors, errors, comparison_data = self.aggregate_test_results(self.tests_results)

        if self.galloper:
            with open("/tmp/config.yaml", "r") as f:
                self.config_file = f.read()
            data = {'arguments': json.dumps(self.args), 'test_results': json.dumps(comparison_data),
                    'config_file': json.dumps(self.config_file), 'aggregated_errors': json.dumps(aggregated_errors),
                    'errors': json.dumps(errors)}
            headers = {'content-type': 'application/json'}
            r = requests.post(self.galloper, json=data, headers=headers)
            print(r.text)
        else:
            try:
                from perfreporter.post_processor import PostProcessor
            except Exception as e:
                print(e)
            post_processor = PostProcessor(self.args, aggregated_errors, errors, comparison_data)
            post_processor.distributed_mode_post_processing()

    def aggregate_test_results(self, test_results):
        errors = []
        aggregated_errors = {}
        for test in test_results:
            errors.extend(json.loads(test['errors']))
            aggregated_err = json.loads(test['aggregated_errors'])
            for err in aggregated_err:
                if err not in aggregated_errors:
                    aggregated_errors[err] = aggregated_err[err]
                else:
                    aggregated_errors[err]['Error count'] = int(aggregated_errors[err]['Error count']) \
                                                            + int(aggregated_err[err]['Error count'])

        results = {}
        for test in test_results:
            comparison_info = json.loads(test['test_info'])
            for key in comparison_info:
                if key not in results:
                    results[key] = {
                        "total": 0,
                        "KO": 0,
                        "OK": 0,
                        "1xx": 0,
                        "2xx": 0,
                        "3xx": 0,
                        "4xx": 0,
                        "5xx": 0,
                        'NaN': 0,
                        "users": 0,
                        "method": comparison_info[key]["method"],
                        "request_name": comparison_info[key]['request_name'],
                        "duration": comparison_info[key]['duration'],
                        "simulation": comparison_info[key]['simulation'],
                        "test_type": comparison_info[key]['test_type'],
                        "build_id": comparison_info[key]['build_id']
                    }
                results[key]['users'] += comparison_info[key]['users']
                results[key]['total'] += comparison_info[key]['total']
                results[key]['KO'] += comparison_info[key]['KO']
                results[key]['OK'] += comparison_info[key]['OK']
                results[key]['1xx'] += comparison_info[key]['1xx']
                results[key]['2xx'] += comparison_info[key]['2xx']
                results[key]['3xx'] += comparison_info[key]['3xx']
                results[key]['4xx'] += comparison_info[key]['4xx']
                results[key]['5xx'] += comparison_info[key]['5xx']
                results[key]['NaN'] += comparison_info[key]['NaN']

        comparison = []
        for req in results:
            comparison.append(results[req])
        self.args['users'] = comparison[0]['users']
        return aggregated_errors, errors, comparison
