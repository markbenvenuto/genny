#!/bin/bash

# run_workloads.sh

WORKLOADS=$(ls -1 data/*.yml)

echo $WORKLOADS

for work in $WORKLOADS
do

    echo $work
    echo ./run-genny workload $work
    time ./run-genny workload $work
    echo "-------------------------------------------------------------------------------------------------------------------------------"
done