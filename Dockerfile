FROM amazonlinux:2 as base

# Tips
# Cleanup everything
# docker system prune
# Build:
# DOCKER_BUILDKIT=1 docker build -t genny
# Evaluate:
# docker run --mount type=bind,source=/home/ubuntu/genny/workload,target=/genny/dist/etc/genny/workloads/  --mount type=bind,source=/home/ubuntu/genny/src/phases,target=/genny/dist/etc/genny/phases  genny evaluate workload/UpdateOnly-es1-0-16-16.yml
# Run:
# docker run --mount type=bind,source=/home/ubuntu/genny/workload,target=/genny/dist/etc/genny/workloads/  --mount type=bind,source=/home/ubuntu/genny/src/phases,target=/genny/dist/etc/genny/phases --network host  genny workload -u localhost:27017 dist/etc/genny/workloads/UpdateOnly-es1-0-16-16.yml

RUN yum -y groupinstall Development Tools
RUN yum -y install python3 python3-pip sudo bash git

RUN mkdir -p /{data/mci,genny}
WORKDIR /genny

FROM base as build
ENV USER="root"
RUN curl http://mongodbtoolchain.build.10gen.cc/installer.sh | bash

ADD . .
RUN ./run-genny install -d amazon2

FROM base
COPY --from=build /genny /genny
COPY --from=build /data/mci/gennytoolchain/installed/x64-linux-dynamic/lib/ /data/mci/gennytoolchain/installed/x64-linux-dynamic/lib/

RUN mkdir -p /data/workdir/mongocrypt/
RUN curl https://mciuploads.s3.amazonaws.com/mongodb-mongo-master/mongo_crypt/linux-x86-dynamic-compile-required/b206e0264580e726f2ba4063a435ded5de28d9a2/mongo_crypt_shared_v1-6.3.0-alpha-492-gb206e02.tgz | tar -xvzf - -C /data/workdir/mongocrypt
ENTRYPOINT ["/genny/run-genny"]
CMD ["-h"]