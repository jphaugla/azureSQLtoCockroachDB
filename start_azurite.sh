npm i -g azurite
nohup azurite --location ./.azurite --debug ./.azurite/debug.log >.azurite/debug.log 2>&1 &

