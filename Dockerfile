##################################################################################
#
#  TensorFlow:
#    we want proper GPU tensorflow support + the ability to use Jupyter
#    in case we're running locally (likely will not work on Hyak)
#    we will later on update the library version on TF, but this gets us
#    all of the GPU-comm setup bullshit
#
##################################################################################
FROM mccoygroup/centos-mpi:ompi-3-1-4

##################################################################################
#
#  Utilities:
#    we bundle stuff like gfortran that is potentially useful for what we do
#
##################################################################################

# May need to do yum install libgfortran5 analog
#RUN apt-get install -y libgfortran5 && \
#    apt-get install -y libgfortran3 && \

RUN yum install -y \
        libgfortran \
        libgomp \
        gcc-c++

RUN yum-config-manager --add-repo https://yum.repos.intel.com/mkl/setup/intel-mkl.repo && \
    rpm --import https://yum.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS-2019.PUB && \
    yum install -y intel-mkl

#    apt-get clean


##################################################################################
#
#  Anaconda:
#    we're going to install the most recent version of Anaconda so that
#    things like h5py come for free & other stuff we like
#    this is pulled directly form the anaconda Dockerfile
#
##################################################################################
ENV PATH=/opt/conda/bin:$PATH

RUN wget --quiet https://repo.anaconda.com/archive/Anaconda3-2020.11-Linux-x86_64.sh -O ~/anaconda.sh
#  RUN wget --quiet https://repo.anaconda.com/archive/Anaconda3-2021.05-Linux-x86_64.sh -O ~/anaconda.sh

RUN /bin/bash ~/anaconda.sh -b -p /opt/conda && \
    rm ~/anaconda.sh

RUN ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc && \
    find /opt/conda/ -follow -type f -name '*.a' -delete && \
    find /opt/conda/ -follow -type f -name '*.js.map' -delete && \
    /opt/conda/bin/conda clean -a -f -y

# END

ADD . /home/McEnv

RUN . /opt/conda/bin/activate base \
  && conda env update --file /home/McEnv/environment.yml --prune


ENTRYPOINT ["/bin/bash", "/home/McEnv/CLI.sh"]
