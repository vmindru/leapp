#!/usr/bin/bash
# Start all defined integration testing VMs
# Based on:
# http://stackoverflow.com/questions/6659689/referring-to-a-file-relative-to-executing-script
# http://stackoverflow.com/questions/2107945/how-to-loop-over-directories-in-linux
pushd "${BASH_SOURCE%/*}" || exit
for vmdef in vmdefs/*/
do
  pushd ${vmdef}
  vagrant up --provision
  popd
done
popd
