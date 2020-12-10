
######################################################################
#                   COMMON FUNCTIONS
######################################################################

# These three are probably never going to be changed, unless we want to change something about how
#  we're distributing the image
MCENV_IMAGE_NAME="mcenv"
#MCENV_PACKAGES_PATH="packages"
#MCENV_SCRIPTS_PATH="scripts"
#MCENV_CONIFG_PATH=""
#MCENV_SOURCE_PATH=""
MCENV_DOCKER_IMAGE="mccoygroup/mcenv:MCENV_IMAGE_NAME"
#MCENV_CONTAINER_RUNNER="docker" # this is to allow for podman support in docker-type envs

function mcoptvalue {

  local flag_pat;
  local value_pat;
  local opt;
  local opt_string;
  local opt_whitespace;
  local OPTARG;
  local OPTIND;

  flag_pat="$1";
  shift
  value_pat="$1";
  shift

  while getopts ":$flag_pat:" opt; do
    case "$opt" in
      $value_pat)
        if [ "$opt_string" != "" ]
          then opt_whitespace=" ";
          else opt_whitespace="";
        fi;
        if [ "$OPTARG" == "" ]
          then OPTARG=true;
        fi
        opt_string="$opt_string$opt_whitespace$OPTARG"
        ;;
    esac;
  done

  OPTIND=1;

  if [ "$opt_string" == "" ]; then
    while getopts "$flag_pat" opt; do
      case "$opt" in
        $value_pat)
          if [ "$opt_string" != "" ]
            then opt_whitespace=" ";
            else opt_whitespace="";
          fi;
          OPTARG=true;
          opt_string="$opt_string$opt_whitespace$OPTARG"
          ;;
      esac;
    done
  fi

  echo $opt_string

}

function mcargcount {
  local arg;
  local arg_count=0;

  for arg in "$@"; do
    if [[ "${arg:0:2}" == "--" ]]; then
      break
    else
      arg_count=$((arg_count+1))
    fi
  done

  echo $arg_count;

}

######################################################################
#                   SYSTEM-SPECIFIC FUNCTIONS
######################################################################

MCENV_OPT_PATTERN=":eV:";
function mcenv_shifter() {

    local config="$MCENV_CONFIG_PATH";
    local scripts="$MCENV_SCRIPTS_PATH";
    local packages="$MCENV_PACKAGES_PATH";
    local img="$MCENV_IMAGE";
    local vols="";
    local do_echo="";
    local arg_count;
    local packages;
    local scripts;
    local lib="$MCENV_SOURCE_PATH";

    arg_count=$(mcargcount $@)
    vols=$(mcoptvalue $MCENV_OPT_PATTERN "V" ${@:1:arg_count})
    do_echo=$(mcoptvalue $MCENV_OPT_PATTERN "e" ${@:1:arg_count})
    if [[ "$vols" != "" ]]; then shift 2; fi
    if [[ "$do_echo" != "" ]]; then shift; fi

    if [[ "$packages" = "" ]]; then
      packages="$PWD/packages";
    fi

    if [[ -d "$packages" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$packages:/home/packages";
      else
        vols="$vols,$packages:/home/packages";
      fi
    fi

    if [[ "$scripts" = "" ]]; then
      scripts="$PWD/scripts";
    fi

    if [[ -d "$scripts" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$scripts:/home/scripts";
      else
        vols="$vols,$scripts:/home/scripts";
      fi
    fi

    if [[ "$config" = "" ]]; then
      config="$PWD/config";
    fi

    if [[ -d "$config" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$packages:/home/packages";
      else
        vols="$vols,$packages:/home/packages";
      fi
    fi

    if [[ "$lib" != "" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$lib:/home/McEnv";
      else
        vols="$vols,$lib:/home/McEnv";
      fi
    fi

    if [[ "$img" = "" ]]; then
      img="$MCENV_SHIFTER_IMAGE";
    fi
    img="--image=$img";

    local escaped=",";
    local real=" --volume=";
    vols=${vols//$escaped/$real}
    vols="--volume=$vols";

    # Set the entrypoint and define any args we need to pass
    cmd="shifter $img $vols"
    if [[ "$enter" == "" ]]; then
      enter="/bin/bash /home/McEnv/CLI.sh"
    fi
    cmd="$cmd $enter"

    #We might want to just echo the command
    if [[ "$do_echo" == "" ]]; then
      $cmd $call $@
      if [[ "$cmd2" != "" ]]; then
        $cmd2
      fi
    else
      echo "$cmd $call"
      if [[ "$cmd2" != "" ]]; then
        echo "&&$cmd2"
      fi
    fi
}

function mcenv_singularity() {

    local config="$MCENV_CONFIG_PATH";
    local scripts="$MCENV_SCRIPTS_PATH";
    local packages="$MCENV_PACKAGES_PATH";
    local img="$MCENV_IMAGE";
    local vols="";
    local do_echo="";
    local arg_count;
    local packages;
    local scripts;
    local lib="$MCENV_SOURCE_PATH";

    arg_count=$(mcargcount $@)
    vols=$(mcoptvalue $MCENV_OPT_PATTERN "V" ${@:1:arg_count})
    do_echo=$(mcoptvalue $MCENV_OPT_PATTERN "e" ${@:1:arg_count})
    if [[ "$vols" != "" ]]; then shift 2; fi
    if [[ "$do_echo" != "" ]]; then shift; fi

    if [[ "$packages" = "" ]]; then
      packages="$PWD/packages";
    fi

    if [[ -d "$packages" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$packages:/home/packages";
      else
        vols="$vols,$packages:/home/packages";
      fi
    fi

    if [[ "$scripts" = "" ]]; then
      scripts="$PWD/scripts";
    fi

    if [[ -d "$scripts" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$scripts:/home/scripts";
      else
        vols="$vols,$scripts:/home/scripts";
      fi
    fi

    if [[ "$config" = "" ]]; then
      config="$PWD/config";
    fi

    if [[ -d "$config" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$packages:/home/packages";
      else
        vols="$vols,$packages:/home/packages";
      fi
    fi

    if [[ "$lib" != "" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$lib:/home/McEnv";
      else
        vols="$vols,$lib:/home/McEnv";
      fi
    fi

    if [[ "$img" = "" ]]; then
      img="$MCENV_IMAGE_NAME.sif";
    fi

    # Set the entrypoint and define any args we need to pass
    cmd="singularity run --bind $vols"

    #We might want to just echo the command
    if [[ "$do_echo" == "" ]]; then
      $cmd $img $@
    else
      echo "$cmd $img"
    fi

}

function mcenv_docker() {

    local runner="$MCENV_CONTAINER_RUNNER";
    local config="$MCENV_CONFIG_PATH";
    local scripts="$MCENV_SCRIPTS_PATH";
    local packages="$MCENV_PACKAGES_PATH";
    local img="$MCENV_IMAGE";
    local vols="";
    local do_echo="";
    local arg_count;
    local packages;
    local scripts;
    local lib="$MCENV_SOURCE_PATH";

    arg_count=$(mcargcount $@)
    vols=$(mcoptvalue $MCENV_OPT_PATTERN "V" ${@:1:arg_count})
    do_echo=$(mcoptvalue $MCENV_OPT_PATTERN "e" ${@:1:arg_count})
    if [[ "$vols" != "" ]]; then shift 2; fi
    if [[ "$do_echo" != "" ]]; then shift; fi

    if [[ "$packages" = "" ]]; then
      packages="$PWD/packages";
    fi

    if [[ -d "$packages" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$packages:/home/packages";
      else
        vols="$vols,$packages:/home/packages";
      fi
    fi

    if [[ "$scripts" = "" ]]; then
      scripts="$PWD/scripts";
    fi

    if [[ -d "$scripts" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$scripts:/home/scripts";
      else
        vols="$vols,$scripts:/home/scripts";
      fi
    fi

    if [[ "$config" = "" ]]; then
      config="$PWD/config";
    fi

    if [[ -d "$config" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$config:/home/packages";
      else
        vols="$vols,$packages:/home/packages";
      fi
    fi

    if [[ "$lib" != "" ]]; then
      if [[ "$vols" == "" ]]; then
        vols="$lib:/home/McEnv";
      else
        vols="$vols,$lib:/home/McEnv";
      fi
    fi

    if [[ "$img" = "" ]]; then
      img="$MCENV_IMAGE_NAME";
    fi

    if [[ "$vols" != "" ]]; then
      local escaped=",";
      local real=" --mount type=bind,source=";
      vols=${vols//$escaped/$real}
      escaped=":";
      real=",target="
      vols=${vols//$escaped/$real}
      vols="--mount type=bind,source=$vols";
    fi

    if [[ "$runner" == "" ]]; then
      runner="docker"
    fi
    # Set the entrypoint and define any args we need to pass
    cmd="$runner run --rm $vols -it"

    #We might want to just echo the command
    if [[ "$do_echo" == "" ]]; then
      $cmd $img $@
    else
      echo "$cmd $img"
    fi
}

function mcenv() {

  local img="$MCENV_IMAGE";
  local cmd;

  # if shifter exists at all...
  if [[ -x "/usr/bin/shifter" ]]; then
    cmd="mcenv_shifter"
  fi

  # if our image is already tagged as a .sif
  if [[ "$img" == *".sif" ]] && [[ "$cmd" == "" ]]; then
    cmd="mcenv_singularity";
  fi

  # if we've got a .sif file we can run
  if [[ "$img" = "" ]] && [[ -f "$PWD/$MCENV_IMAGE_NAME.sif" ]] && [[ "$cmd" == "" ]]; then
    cmd="mcenv_singularity";
  fi

  if [[ "$cmd" == "" ]]; then
    cmd="mcenv_docker";
  fi

  $cmd $@;

}