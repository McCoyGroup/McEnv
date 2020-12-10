
FROM ubuntu:latest

# Update Ubuntu stuff
RUN apt-get update && yes|apt-get upgrade
# Adding wget and bzip2
RUN apt-get install -y wget bzip2

##################################################################################
#
#  ANACONDA:
#    rather than manage dependencies & install all the shit we _might_ need,
#    it seems easier to just use conda, esp. in this kind of environment
#
##################################################################################
# Anaconda installing
RUN wget https://repo.anaconda.com/archive/Anaconda3-2020.11-Linux-x86_64.sh
RUN bash Anaconda3-2020.11-Linux-x86_64.sh -b
RUN rm Anaconda3-2020.11-Linux-x86_64.sh
# Set path to conda
ENV PATH /root/anaconda3/bin:$PATH
# Updating Anaconda packages
RUN conda update conda
RUN conda update anaconda
RUN conda update --all


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

ENTRYPOINT ["/bin/bash", "/home/McEnv/CLI.sh"]