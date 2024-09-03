#!/bin/bash
GETPRODUCT=900
POSTCHECKOUT=30
GETCART=5000
POSTCART=2600
CART=1000
RATE=10

tmux kill-session -t session4
tmux new-session -d -s session4


tmux new-window -d -t session4 "locust -f locust_online_boutique.py --host=http://10.8.0.4:30440 -u $POSTCHECKOUT -r 3 --headless  --tags postcheckout < ports/8928"



tmux kill-session -t session5
tmux new-session -d -s session5


tmux new-window -d -t session5 "locust -f locust_online_boutique.py --host=http://10.8.0.4:30440 -u $GETPRODUCT -r 90 --headless  --tags getproduct < ports/8929"



tmux kill-session -t session6
tmux new-session -d -s session6


tmux new-window -d -t session6 "locust -f locust_online_boutique.py --host=http://10.8.0.4:30440 -u $CART -r 100 --headless  --tags getcart postcart emptycart < ports/8930"
