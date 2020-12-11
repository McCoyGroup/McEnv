##################################################################################
#
#  TensorFlow:
#    we want proper GPU tensorflow support + the ability to use Jupyter
#    in case we're running locally (likely will not work on Hyak)
#
##################################################################################
FROM tensorflow/tensorflow:nightly-gpu-jupyter

##################################################################################
#
#  Anaconda:
#    we're going to install the most recent version of Anaconda so that
#    things like h5py come for free & other stuff we like
#    this is pulled directly form the anaconda Dockerfile
#
##################################################################################
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV PATH=/opt/conda/bin:$PATH

RUN apt-get update --fix-missing && apt-get install -y wget bzip2 ca-certificates \
    libglib2.0-0 libxext6 libsm6 libxrender1 \
    git mercurial subversion && \
    apt-get clean

RUN wget --quiet https://repo.anaconda.com/archive/Anaconda3-2020.11-Linux-x86_64.sh -O ~/anaconda.sh

RUN /bin/bash ~/anaconda.sh -b -p /opt/conda && \
    rm ~/anaconda.sh

RUN ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc && \
    find /opt/conda/ -follow -type f -name '*.a' -delete && \
    find /opt/conda/ -follow -type f -name '*.js.map' -delete && \
    /opt/conda/bin/conda clean -afy

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