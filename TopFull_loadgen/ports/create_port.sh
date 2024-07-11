#!/bin/bash

start=8888
end=8930

for i in $(seq $start $end)
do
   echo $i > "$i"
done
