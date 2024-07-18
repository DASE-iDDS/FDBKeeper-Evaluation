#! /usr/bin/env python3

import argparse
import os
import subprocess
import json
import logging
import signal

class Host(dict):
    def rsh(self):
        cmds = []
        if self["password"]:
            cmds += ["sshpass", "-p", self["password"]]
        cmds += ["ssh", self["host"]]
        return cmds

def ansible_adhoc(args, task_result_fn=lambda x: x):
    # Set environment variable ANSIBLE_STDOUT_CALLBACK
    os.environ["ANSIBLE_STDOUT_CALLBACK"] = "ansible.posix.json"
    os.environ["ANSIBLE_LOAD_CALLBACK_PLUGINS"] = "1"
    
    script_dir = os.path.dirname(os.path.realpath(__file__))
    parent_dir = os.path.abspath(os.path.join(script_dir, os.pardir))
    
    ansible_cmd = ["ansible"] + args
    logging.debug(f"Exec {ansible_cmd}")
    result = subprocess.run(ansible_cmd, cwd=parent_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    if result.returncode != 0 and not result.stdout:
        raise Exception("Ansible command failed")
    
    try:
        json_output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        if result.returncode != 0:
            raise Exception("Ansible command failed: " + result.stdout)
        else:
            raise Exception("Failed to parse Ansible", e)
    
    task_results = {}
    for play in json_output["plays"]:
        for task in play["tasks"]:
            for h, r in task["hosts"].items():
                task_results[h] = task_result_fn(r)
    
    return (result.returncode, task_results)

def ansible_debug_msg(host, debug_msg):
    ret, msgs = ansible_adhoc([
        host,
        "-m", "debug",
        "-a", f"msg={debug_msg}"
    ], task_result_fn=lambda x: x["msg"])

    if ret != 0:
        raise Exception(f"Ansible debug failed: {msgs}")

    return msgs

def remote_keeper_bench(host, keeper_bench_args, keeper_bench="./keeper-bench"):
    cmd = host.rsh() + [keeper_bench] + keeper_bench_args
    logging.debug(f"Exec: {cmd}")

    p = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        process_group=0
    )

    class Handler:
        def wait(self):
            p.wait()
            return p

        def kill(self):
            if p.poll() is not None:
                return

            logging.debug(f"Try to kill keeper-bench on {host}")
            subprocess.run(host.rsh() + [
                "sh", "-xc",
                f"\'kill -INT $(pgrep -f {keeper_bench})\'"
            ])
            while True:
                try:
                    p.wait()
                    break
                except KeyboardInterrupt:
                    pass

    return Handler()

def init_bench_data(host, workload, keeper_bench="./keeper-bench", keeper_bench_config_dir="/etc/keeper-bench"):
    logging.debug("Init bench data")
    h = remote_keeper_bench(host, [
        "--config", f"{keeper_bench_config_dir}/{workload}.yml",
        "--init"
    ], keeper_bench=keeper_bench)
    result = h.wait()
    if result.returncode != 0:
        raise Exception(f"Failed to init bench data")

def do_bench_bg(host, workload, keeper_bench="./keeper-bench", keeper_bench_config_dir="/etc/keeper-bench", concurrency=1, time_limit=None, iterations=None):
    args = ["--config", f"{keeper_bench_config_dir}/{workload}.yml", "--noinit"]
    if concurrency > 1:
        args += ["-c", str(concurrency)]
    if time_limit is not None:
        args += ["--time-limit", str(time_limit)]
    if iterations is not None and iterations > 0:
        args += ["--iterations", str(iterations)]
    return remote_keeper_bench(host, args, keeper_bench=keeper_bench)

def main(workload, concurrency, process_size, noinit, time_limit, iterations):
    logging.info(f"Workload: {workload}")
    logging.info(f"Concurrency: {concurrency}")
    logging.info(f"Process Size: {process_size}")

    avaiable_clients = list(map(Host, ansible_debug_msg("clients", '{{ { "host": ansible_user + "@" + public_ipv4, "password": ansible_password | default(None) } }}').values()))
    if not avaiable_clients:
        raise Exception("No avaiable client")
    logging.info(f"Avaiable clients: {avaiable_clients}")

    concurrency_per_process, concurrency_remain = divmod(concurrency, process_size)
    iterations_per_process, iterations_remain = divmod(iterations or 0, process_size)
    args_pre_process = []
    for i in range(0, process_size):
        concurrency = concurrency_per_process
        if concurrency_remain:
            concurrency += 1
            concurrency_remain -= 1
        iterations = iterations_per_process
        if iterations_remain:
            iterations += 1
            iterations_remain -= 1

        args_pre_process.append({
            "host": avaiable_clients[i % len(avaiable_clients)],
            "concurrency": concurrency,
            "time_limit": time_limit,
            "iterations": iterations,
        })
    logging.debug(f"Processes: {args_pre_process}")

    if not noinit:
        init_bench_data(avaiable_clients[0], workload)

    logging.debug(f"Start {len(args_pre_process)} process")
    bench_process_handlers = []
    for args in args_pre_process:
        bench_process_handlers.append(do_bench_bg(workload=workload, **args))

    try:
        for h in bench_process_handlers:
            r = h.wait()
            if r.returncode != 0:
                raise Exception(f"Non-zero return code: {r.returncode}")
        return 0
    except:
        logging.exception("keeper bench failed", exc_info=True)
        for h in bench_process_handlers:
            h.kill()
        return 1

if __name__ == "__main__":
    logging.root.setLevel(logging.DEBUG)

    try:
        import colorlog
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(colorlog.ColoredFormatter('%(log_color)s%(levelname)-.4s%(reset)s %(message)s'))
        logging.root.addHandler(stream_handler)
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Process workload parameters.")
    parser.add_argument("-w", "--workload", type=str, help="Name of the workload", required=True)
    parser.add_argument("-x", "--concurrency", type=int, help="Concurrency value (1 will be overwritten by the configuration file)", default=1)
    parser.add_argument("-p", "--process_size", type=int, help="Process size value", default=1)
    parser.add_argument("-t", "--time_limit", type=int, help="Time limit (seconds)", default=None)
    parser.add_argument("-i", "--iterations", type=int, help="Amount of queries", default=None)
    parser.add_argument("--noinit", help="Skip init data", default=False, action='store_true')
    args = parser.parse_args()

    ret = main(**vars(args))
    logging.info("Bye")
    exit(ret)
