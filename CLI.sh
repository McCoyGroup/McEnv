
######################################################################
#                   MCENV CLI
######################################################################
# Provides a simple set of functions to make it easier to use
# supports bootstrapping to make it possible just have the one
# image, since we don't expect to update it particularly often

export PYTHONPATH=$PYTHONPATH:/home/packages
if [[ "$1" == "get_env" ]]; then
    echo "$(cat /home/McEnv/env.sh)"
elif [[ "$1" == "--exec" ]]; then
      shift 1;
      cmd="$1"
      shift 1;
      $cmd $@
elif [[ "$1" == "--sh" ]]; then
  shift 1;
  /bin/bash $@
else
  python3 "/home/McEnv/CLI.py" $@
fi