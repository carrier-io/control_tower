#!/bin/bash

#on_exit() {
#    echo "Trapping"
#}
#
#trap on_exit SIGTERM SIGKILL SIGINT SIGHUP EXIT
#
#run "$@" &
#wait
run "$@"