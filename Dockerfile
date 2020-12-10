
FROM continuumio/anaconda3

##################################################################################
#
#  McEnv:
#    we're going to bundle a small set of useful scripts, but not introduce
#    any complicated runtime logic or any of that jazz
#    this is inspired by the earlier RynLib container which had a similar sort
#    of run script, but which also had much more complicated eval. semantics
#
##################################################################################

ADD . /home/McEnv

WORKDIR /home

ENTRYPOINT ["/bin/bash", "/home/McEnv/CLI.sh"]