# syntax=docker/dockerfile:1.4
FROM amazonlinux:2 as base

# Tips
# Cleanup everything
# docker system prune
# Build:
# DOCKER_BUILDKIT=1 docker build -t genny .
# Evaluate
# docker run --mount type=bind,source=/home/ubuntu/genny/src/workloads,target=/genny/src/genny/dist/etc/genny/workloads/  --mount type=bind,source=/home/ubuntu/genny/src/phases,target=/genny/src/genny/dist/etc/genny/phases genny evaluate /genny/src/genny/dist/etc/genny/workloads/encryption_qualification/medical_workload-credit_cards-50-50.yml
# Run:
# docker run --mount type=bind,source=/home/ubuntu/genny/src/workloads,target=/genny/src/genny/dist/etc/genny/workloads/  --mount type=bind,source=/home/ubuntu/genny/src/phases,target=/genny/src/genny/dist/etc/genny/phases --net host genny workload -u localhost:27017 /genny/src/genny/dist/etc/genny/workloads/encryption_qualification/medical_workload-credit_cards-50-50.yml

RUN yum -y groupinstall Development Tools && yum -y install python3 python3-pip sudo bash git && yum clean all && rm -rf /var/cache/yum

ENV USER="root"
RUN curl http://mongodbtoolchain.build.10gen.cc/installer.sh | bash

RUN mkdir -p /{data/mci,genny/src/genny}
WORKDIR /genny/src/genny

RUN mkdir -p build/curator
RUN curl https://s3.amazonaws.com/boxes.10gen.com/build/curator/curator-dist-rhel70-3df28d2514d4c4de7c903d027e43f3ee48bf8ec1.tar.gz | tar -xvzf - -C build/curator

FROM base as build

RUN mkdir -p /data/mci/gennytoolchain
RUN curl https://s3.amazonaws.com/mciuploads/genny-toolchain/genny_toolchain_amazon2_b563d3ba01a8b1a4fa4249e9eb0ad5c9bc11816b_22_12_12_21_24_44/gennytoolchain.tgz | tar -xvzf - -C /data/mci/gennytoolchain

COPY --link LICENSE.txt THIRD-PARTY-NOTICES.txt  CMakeLists.txt pyproject.toml run-genny run_workloads.sh .
COPY --link ./cmake/ ./cmake/
COPY --link ./src/ ./src
COPY --link ./.git/ ./.git
RUN ./run-genny install -d amazon2

FROM base
RUN mkdir -p /media/ebs/workdir/mongocrypt/
RUN curl https://mciuploads.s3.amazonaws.com/mongodb-mongo-master/mongo_crypt/linux-x86-dynamic-compile-required/b206e0264580e726f2ba4063a435ded5de28d9a2/mongo_crypt_shared_v1-6.3.0-alpha-492-gb206e02.tgz | tar -xvzf - -C /media/ebs/workdir/mongocrypt

COPY --from=build /genny /genny
COPY --from=build /data/mci/gennytoolchain/installed/x64-linux-dynamic/lib/ /data/mci/gennytoolchain/installed/x64-linux-dynamic/lib/

WORKDIR /genny
ENTRYPOINT ["/genny/src/genny/run-genny"]
CMD ["-h"]