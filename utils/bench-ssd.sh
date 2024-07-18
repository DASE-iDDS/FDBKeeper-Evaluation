#! /bin/sh

set -e
SCRIPT_ROOT="$(realpath "$(dirname "$0")")"
DATA_FILE="$1"

fio --loops=5 --size=1000m --filename="$DATA_FILE" \
  --stonewall --ioengine=libaio --direct=1 \
  --name=Seqread --bs=1m --rw=read \
  --name=Seqwrite --bs=1m --rw=write \
  --name=512Kread --bs=512k --rw=randread \
  --name=512Kwrite --bs=512k --rw=randwrite \
  --name=4kQD64read --bs=4k --iodepth=64 --rw=randread \
  --name=4kQD64write --bs=4k --iodepth=64 --rw=randwrite
