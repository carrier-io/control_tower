import json
import statistics
from perfreporter.reporter import Reporter


class PostProcessor:

    def __init__(self, tests_results, build_id, test_type, simulation, comparison_metric, request_count):
        self.tests_results = tests_results
        self.args = {"simulation": simulation, "type": test_type, "comparison_metric": comparison_metric,
                     "build_id": build_id, "request_count": request_count}

    def aggregate_results(self):
        aggregated_errors, errors = self.aggregate_errors(self.tests_results)
        performance_degradation_rate, compare_with_baseline = self.aggregate_comparison_results(self.tests_results, self.args)
        missed_threshold_rate, compare_with_thresholds = self.aggregate_thresholds_results(self.tests_results, self.args)
        reporter = Reporter()
        print("Parsing config file ...")
        loki, rp_service, jira_service = reporter.parse_config_file(self.args)

        reporter.report_errors(aggregated_errors, errors, self.args, loki, rp_service, jira_service)

        reporter.report_performance_degradation(performance_degradation_rate, compare_with_baseline, rp_service,
                                                jira_service)

        reporter.report_missed_thresholds(missed_threshold_rate, compare_with_thresholds, rp_service, jira_service)

    @staticmethod
    def aggregate_errors(test_results):
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
        return aggregated_errors, errors

    @staticmethod
    def aggregate_comparison_results(test_results, args):
        compare_with_baseline = []
        performance_degradation_rate = 0
        tmp_map = {}
        for test in test_results:
            comparison_info = json.loads(test['compare_with_baseline'])
            for request in comparison_info:
                if request['request_name'] not in tmp_map:
                    tmp_map[request['request_name']] = {"response_time": [request['response_time']],
                                                        "baseline": request['baseline']}
                else:
                    tmp_map[request['request_name']]['response_time'].append(request['response_time'])
        for request in tmp_map:
            compare_with_baseline.append({'request_name': request,
                                          'response_time': int(statistics.median(tmp_map[request]['response_time'])),
                                          'baseline': tmp_map[request]['baseline']})

        if compare_with_baseline:
            performance_degradation_rate = round(float(len(tmp_map) / int(args['request_count'])) * 100, 2)
        return performance_degradation_rate, compare_with_baseline

    @staticmethod
    def aggregate_thresholds_results(test_results, args):
        compare_with_thresholds = []
        missed_threshold_rate = 0
        tmp_map = {}
        for test in test_results:
            thresholds_info = json.loads(test['compare_with_thresholds'])
            for request in thresholds_info:
                if request['request_name'] not in tmp_map:
                    tmp_map[request['request_name']] = {"response_time": [request['response_time']],
                                                        "yellow": request['yellow'], "red": request['red']}
                else:
                    tmp_map[request['request_name']]['response_time'].append(request['response_time'])
        for request in tmp_map:
            response_time = int(statistics.median(tmp_map[request]['response_time']))
            threshold = 'yellow' if response_time < int(tmp_map[request]['red']) else 'red'
            compare_with_thresholds.append({"request_name": request, "response_time": response_time,
                                            "threshold": threshold, "yellow": tmp_map[request]['yellow'],
                                            "red": tmp_map[request]['red']})
        if compare_with_thresholds:
            missed_threshold_rate = round(float(len(tmp_map) / int(args['request_count'])) * 100, 2)
        return missed_threshold_rate, compare_with_thresholds
