#!/bin/bash
tmux kill-session -t session2
tmux new-session -d -s session2

LOCUST="locust_train_ticket.py"

HIGHSPEED=20
NORMALSPEED=20
ORDER=20
ORDEROTHER=20
FOOD=20
PAYMENT=20

tmux new-window -d -t session2 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags high_speed_ticket --headless -u $HIGHSPEED -r 20 --run-time 20m < ports/8894"
tmux new-window -d -t session2 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags normal_speed_ticket --headless -u $NORMALSPEED -r 20 --run-time 20m < ports/8895"
tmux new-window -d -t session2 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags query_order --headless -u $ORDER -r 20 --run-time 20m < ports/8896"
tmux new-window -d -t session2 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags query_order_other --headless -u $ORDEROTHER -r 20 --run-time 20m < ports/8897"
tmux new-window -d -t session2 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags query_food --headless -u $FOOD -r 40 --run-time 20m < ports/8898"
tmux new-window -d -t session2 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags query_payment --headless -u $PAYMENT -r 100 --run-time 20m < ports/8899"
