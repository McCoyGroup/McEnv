
# McEnv

This is a light-weight template for a container that provides a standardized environment so that code written for a local machine can run just as cleanly on an HPC (both Hyak/Mox and NeRSC/Cori) are currently supported.

Currently we just package Anaconda and `gfort`, but like we can include whatever we need.

Basically just provides a really simple dispatch to `docker`/`singularity`/`shifter` depending on the locale.
More functionality can easily be packed in (or the base container can be replaced) as need be.

## Getting Started

To install on Mox, use Singularity to pull it in the directory you want to install to. 
This will look like

```shell script
module load singularity
singularity pull mcenv.sif docker://mccoygroup/mcenv:latest
```

You can then load the built-in support script by

```shell script
env_file=/tmp/mcenv.sh
./mcenv.sif get_env > $env_file
. $env_file
rm env_file
```

The built in `mcenv` function will help set up the environment, in particular by managing calls into docker`/`singularity`/`shifter` and providing two env variables

```lang-none
MCENV_PACKAGES_PATH - path to be prepended to `PYTHONPATH` to provide a custom packages directory that can be pointed to different places
MCENV_SCRIPTS_PATH - path to a scripts directory that python will look into for runnable script files
```