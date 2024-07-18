#! /usr/bin/env python3

import subprocess
import json
import time
import sys
import atexit
import random
import os
import glob

def get_fdb_status():
    result = subprocess.run('fdbcli --exec "status json"', shell=True, stdout=subprocess.PIPE, text=True)

    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        raise Exception(f"Command failed with return code {result.returncode}" + ((": " + result.stdout.rstrip('\n')) if result.stdout else ""))

class Metric:
    def __init__(self, name, type, value, labels = None):
        self.name = name
        self.type = type
        self.value = value
        self.labels = labels or {}

def get_metrics(status):
    metrics = []

    if not status["client"]["database_status"]["available"]:
        metrics.append(Metric("database_status_available", "gauge", 0))
        return metrics

    metrics.append(Metric("database_status_available", "gauge", 1))

    for k, v in status["cluster"]["latency_probe"].items():
        metrics.append(Metric(f"cluster_latency_probe_{k}", "gauge", v))

    for process, process_status in status["cluster"]["processes"].items():
        labels = {
            "process": process,
            "address": process_status["address"],
            "class_type": process_status["class_type"]
        }
        metrics.append(Metric(f"cluster_process_cpu_usage", "gauge", process_status["cpu"]["usage_cores"], labels))
        metrics.append(Metric(f"cluster_process_busy", "gauge", process_status["run_loop_busy"], labels))

        for role in process_status["roles"]:
            role_labels = {
                **labels,
                "role": role["role"]
            }
            metrics.append(Metric(f"cluster_process_role", "gauge", 1, role_labels))

    for k, v in status["cluster"]["workload"]["transactions"].items():
        metrics.append(Metric(f"cluster_workload_transactions_{k}", "counter", v["counter"]))

    for k, v in status["cluster"]["workload"]["operations"].items():
        metrics.append(Metric(f"cluster_workload_operations_{k}", "counter", v["counter"]))

    metrics.append(Metric("cluster_qos_transactions_per_second_limit", "gauge", status["cluster"]["qos"]["transactions_per_second_limit"]))

    return metrics


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print(f"usage: {sys.argv[0]} /path/to/output/prom", file=sys.stderr)
        sys.exit(1)

    output_path = sys.argv[1]
    @atexit.register
    def cleanup():
        print(f"Cleanup...", file=sys.stderr)
        if os.path.exists(output_path):
            os.remove(output_path)
        for f in glob.glob(output_path + ".*"):
            os.remove(f)

    while True:
        try:
            status = get_fdb_status()

            typed_set = set()
            output_tmp_path = output_path + "." + str(random.randint(1000, 9999))
            with open(output_tmp_path, 'x') as f:
                for m in get_metrics(status):
                    name = f'fdb_{m.name}'

                    labels = ','.join([f'{k}="{v}"' for k, v in m.labels.items()])
                    if labels:
                        labels = f'{{{labels}}}'

                    if name not in typed_set:
                        f.write(f'# TYPE {name} {m.type}\n')
                        typed_set.add(name)
                    f.write(f'{name}{labels} {m.value}\n')

            os.replace(output_tmp_path, output_path)

        except Exception as e:
            print(f"Failed to export metric: {e}", flush=True, file=sys.stderr)

        time.sleep(1)
