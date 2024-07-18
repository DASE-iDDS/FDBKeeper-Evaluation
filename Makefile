COMMAND_WRAPPER = pipenv run
ANSIBLE_PLAYBOOK = $(COMMAND_WRAPPER) ansible-playbook

all:

install:
	$(ANSIBLE_PLAYBOOK) ./playbooks/setup-bench.yml $(if $(SKIP_GENERATE_WORKLOADS),--skip-tags generate-workloads)

install-debug:
	$(ANSIBLE_PLAYBOOK) ./playbooks/setup-bench.yml -e debug_bench=true

generate-workloads:
	$(ANSIBLE_PLAYBOOK) ./playbooks/setup-bench.yml -t generate-workloads

deploy-zk:
	$(ANSIBLE_PLAYBOOK) ./playbooks/setup-zk.yml

redeploy-zk:
	$(ANSIBLE_PLAYBOOK) ./playbooks/setup-zk.yml

disable-zk:
	$(ANSIBLE_PLAYBOOK) ./playbooks/setup-zk.yml \
		--tag disable-zk

deploy-fdb:
	$(ANSIBLE_PLAYBOOK) ./playbooks/setup-fdb.yml

redeploy-fdb:
	$(ANSIBLE_PLAYBOOK) ./playbooks/setup-fdb.yml \
		--skip-tag install-deb

clear-fdb:
	$(COMMAND_WRAPPER) ./utils/rsh "servers[0]" fdbcli --exec \
		'writemode on; clearrange "" "\xff"'

disable-fdb:
	$(ANSIBLE_PLAYBOOK) ./playbooks/setup-fdb.yml \
		--tag disable-fdb

cleanup-running-bench:
	-$(COMMAND_WRAPPER) ansible clients -m shell -a "killall keeper-bench"
	-$(COMMAND_WRAPPER) ansible clients -m script -a "./utils/pushgateway-deleteall.sh 127.0.0.1:9030"