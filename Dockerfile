##################################################################################
#
#  TensorFlow:
#    we want proper GPU tensorflow support + the ability to use Jupyter
#    in case we're running locally (likely will not work on Hyak)
#    we will later on update the library version on TF, but this gets us
#    all of the GPU-comm setup bullshit
#
##################################################################################
FROM mccoygroup/tensorflow-mpi:ompi-3-1-4

##################################################################################
#
#  Anaconda:
#    we're going to install the most recent version of Anaconda so that
#    things like h5py come for free & other stuff we like
#    this is pulled directly form the anaconda Dockerfile
#
##################################################################################
ENV PATH=/opt/conda/bin:$PATH

# RUN wget --quiet https://repo.anaconda.com/archive/Anaconda3-2020.11-Linux-x86_64.sh -O ~/anaconda.sh
RUN wget --quiet https://repo.anaconda.com/archive/Anaconda3-2021.05-Linux-x86_64.sh -O ~/anaconda.sh

RUN /bin/bash ~/anaconda.sh -b -p /opt/conda && \
    rm ~/anaconda.sh

RUN ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc && \
    find /opt/conda/ -follow -type f -name '*.a' -delete && \
    find /opt/conda/ -follow -type f -name '*.js.map' -delete && \
    /opt/conda/bin/conda clean -a -f -y

##################################################################################
#
#   FILE USAGE INFO:
#    For debug purposes want to know how much space we're using
#
##################################################################################

#RUN df -h && \
#    du -sh /opt/ && \
#    du -sh /usr/lib

#RUN pip install mpi4py --disable-pip-version-check

##################################################################################
#
#  Utilities:
#    we bundle stuff like gfortran that is potentially useful for what we do
#
##################################################################################

RUN apt-get install -y gfortran && \
    apt-get install -y libgfortran5 && \
    apt-get install -y libgfortran3 && \

    apt-get clean
    
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

RUN . /opt/conda/bin/activate base \
  && conda env update --file /home/McEnv/environment.yml --prune


ENTRYPOINT ["/bin/bash", "/home/McEnv/CLI.sh"]
