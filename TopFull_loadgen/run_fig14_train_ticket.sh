#!/bin/bash
tmux kill-session -t session1
tmux new-session -d -s session1

LOCUST="locust_train_ticket.py"

HIGHSPEED=180
NORMALSPEED=180
ORDER=180
ORDEROTHER=180
FOOD=380
PAYMENT=90

tmux new-window -d -t session1 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags high_speed_ticket --headless -u $HIGHSPEED -r 20 --run-time 15m < ports/8888"
tmux new-window -d -t session1 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags normal_speed_ticket --headless -u $NORMALSPEED -r 20 --run-time 15m < ports/8889"
tmux new-window -d -t session1 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags query_order --headless -u $ORDER -r 20 --run-time 15m < ports/8890"
tmux new-window -d -t session1 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags query_order_other --headless -u $ORDEROTHER -r 20 --run-time 15m < ports/8891"
tmux new-window -d -t session1 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags query_food --headless -u $FOOD -r 40 --run-time 15m < ports/8892"
tmux new-window -d -t session1 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags query_payment --headless -u $PAYMENT -r 100 --run-time 15m < ports/8900"
tmux new-window -d -t session1 "locust -f $LOCUST --host=http://10.8.0.4:32677 --tags query_payment --headless -u $PAYMENT -r 100 --run-time 15m < ports/8893"
