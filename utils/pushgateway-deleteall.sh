#! /bin/sh

PUSHGATEWAY_URL=${1:?Usage $0 pushgateway_url}

curl -s "$PUSHGATEWAY_URL/metrics" \
    | sed -E \
        -e '/^push_time_seconds/!d' \
        -e 's/^.*\{(.*)\}.*$/\1,/' \
        -e 's/^(.*,)(job="[^"]*",)(.*)$/\2\1\3/' \
        -e 's/,$//' \
        -e 's|[=,]|/|g;s|\"||g' \
        -e "s|^|${PUSHGATEWAY_URL}/metrics/|" \
    | xargs -I{} -t curl -X DELETE {}
