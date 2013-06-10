# run: . blueprints.sh {token} {tenant/account} && open blueprints.jpg
ab -n 3000 -c 30 -H "X-Auth-Token: $1" -g blueprints.dat  http://localhost:8080/$2/blueprints.yaml?details=0
gnuplot blueprints.p
