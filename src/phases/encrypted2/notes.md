TODO
----

python script to run workloads
save dbs
save cedar results
save ftdc metrics?

can we reuse a db?, ask erwin

create clustered collections instead of regular for state collections


Flamegraph
-----------

On CPU flamegraph
----------------
AS Root:

perf record -F 99 -p `pgrep -x mongod` -g sleep 60

IMPORTANT - MUST run perf script as ROOT!!!!! otherwise you will get unknown kernel symbols
perf script > out.perf

AS normal user (can be root)
~/repo/FlameGraph/stackcollapse-perf.pl out.perf > out.folded

cat out.folded | sd "FLECrud-\d+" "FLECrud"  | ~/repo/FlameGraph/flamegraph.pl --width=3000 > flame3.svg
cat find.folded | sd "conn\d+" "conn"| sd "FLECrud-\d+" "FLECrud" | ~/repo/FlameGraph/flamegraph.pl --width=3000 > flame5.svg

Off Cpu flamegraph
---------
./offcputime.py -f --stack-storage-size=10000 -p `pgrep -x mongod` 30 > out3.offcpu

 rg mongo out.offcpu | /home/mark/repo/FlameGraph/flamegraph.pl  --color=io --countname=us --width=3000     --title="Off-CPU Time Flame Graph: idle system" > offcpu.svg

 cat out3.offcpu | sd "conn\d+" "conn"| sd "FLECrud-\d+" "FLECrud" | /home/mark/repo/FlameGraph/flamegraph.pl  --color=io --countname=us --width=3000     --title="Off-CPU Time Flame Graph: idle system" > ~/mongo/offcpu3.svg




===================
Experiment Set q.1: Query unencrypted fields on unencrypted collection
coll = pbl
enc = 0
(qfield, qval) in
(fixed_10, fixed_hf),
(fixed_10, uar),
(uar_[1, 10], uar),
(uar_[1, 10], uar_alllow)
cf in {1, 4, 8, 16}
tc in {1, 4, 8, 16}

Experiment Set q.2: Query unencrypted fields on partially encrypted collection
coll = pbl
enc = 5
(qfield, qval) in
(fixed_10, fixed_hf),
(fixed_10, uar),
(uar_[6, 10], uar),
(uar_[6, 10], uar_alllow)
cf in {1, 4, 8, 16}
tc in {1, 4, 8, 16}

Experiment Set q.3: Query encrypted fields on partially encrypted collection
coll = pbl
enc = 5
(qfield, qval) in
(fixed_1, fixed_hf),
(fixed_1, uar),
(uar_[1, 5], uar),
(uar_[1, 5], uar_alllow)
cf in {1, 4, 8, 16}
tc in {1, 4, 8, 16}

Experiment Set q.4: Query encrypted fields on fully encrypted collection
coll = pbl
enc = 10
(qfield, qval) in
(fixed_1, fixed_hf),
(fixed_1, uar),
(uar_[1, 10], uar),
(uar_[1, 10], uar_alllow)
cf in {1, 4, 8, 16}
tc in {1, 4, 8, 16}

Experiment Set q.5: Check the impact of BSON limit on queries on both encrypted and unencrypted fields
coll = blimit
enc = 5
(qfield, qval) in
(fixed_1, fixed_hf),
(fixed_10, fixed_hf)
cf in {1, 4, 8, 16}
tc in {1, 4, 8, 16}

============

Fields (field):
A field can be either fixed or selected uniformly at random (uar). Moreover, if a document  is partially encrypted, then a field can be encrypted or unencrypted. An experiment sets a field for its operations, using the following notation:
_id: query is on the _id field
fixed_<i>: the query is on field fieldi
uar_[<lb, ub>]: the query is on field chosen uniformly at random from {fieldlb, …, fieldub}. Recall that, by our convention, the first x fields of a document are encrypted, where x can be a value between 1 and 10. Suppose x = 5, then if field is set to  uar_[1, 5] the query chooses an encrypted field uniformly at random whereas if field is set to uar_[6, 10] then the query chooses an unencrypted field uniformly at random.

Values (val):
Given a field f, a value is always selected from the domain of the field f which we denote by Domain(f).  We also partition the values in Domain(f) into 6 buckets {vlf, mlf, lf, hf, mhf, vhf}, based on their frequencies, where the range of each bucket is defined in the table above. A value can be fixed, selected uniformly at random from Domain(f), or selected uniformly at random from a specific bucket/partition.  We now define the notation describing how the values of queries are chosen in experiments:
fixed: a value v from Domain(f) is fixed
fixed_<b>: a value v in bucket b is fixed as follows. If b in {vlf, mlf, hf}, then we select the value in bucket b with the lowest frequency. If b in {hf, mhf, vhf}, we select the value in bucket b with highest frequency.
uar: the value is selected uniformly at random from Domain(f)
uar_<b>: the value is selected uniformly at random from the bucket b.
uar_alllow: the value is selected uniformly at random from buckets {vlf, mlf, lf}
uar_allhigh: the value is selected uniformly at random from buckets {hf, mhf, hf}








=============================


(genny_venv) ➜  genny git:(frequency_map) ✗ ./run-genny workload src/workloads/encrypted3/Query-es2-1-8.yml
Note: NumExpr detected 16 cores but "NUMEXPR_MAX_THREADS" not set, so enforcing safe limit of 8.
NumExpr defaulting to 8 threads.
[info ] [genny.curator       ] Moved existing metrics (presumably from a prior run). cwd=/home/mark/src/genny existing=build/WorkloadOutput/CedarMetrics moved_to=build/WorkloadOutput/CedarMetrics-2022-12-15T002201Z-3bb7bcc9 timestamp=2022-12-15T00:22:01Z
[info ] [genny.curator       ] Starting poplar grpc in the background. command=['/home/mark/src/genny/build/curator/curator', 'poplar', 'grpc'] cwd=/home/mark/src/genny timestamp=2022-12-15T00:22:01Z
[curator] 2022/12/14 19:22:01 [p=info]: starting poplar gRPC service at 'localhost:2288'
{"t":{"$date":"2022-12-15T00:22:03.287Z"},"s":"I",  "c":"NETWORK",  "id":4648601, "ctx":"thread1","msg":"Implicit TCP FastOpen unavailable. If TCP FastOpen is required, set tcpFastOpenServer, tcpFastOpenClient, and tcpFastOpenQueueSize."}
{"t":{"$date":"2022-12-15T00:22:03.371Z"},"s":"I",  "c":"ASIO",     "id":6529201, "ctx":"thread1","msg":"Network interface redundant shutdown","attr":{"state":"Stopped"}}
{"t":{"$date":"2022-12-15T00:22:03.372Z"},"s":"I",  "c":"ASIO",     "id":22582,   "ctx":"thread1","msg":"Killing all outstanding egress activity."}
[2022-12-14 19:22:03.373786] [0x00007fa0febff6c0] [info]    Constructing pool with MongoURI 'mongodb://localhost:27017/?appName=Genny&maxPoolSize=400'
[2022-12-14 19:22:04.379149] [0x00007f9f315d06c0] [info]    Beginning phase 0
[2022-12-14 19:27:03.132642] [0x00007f9f35dd96c0] [info]    Phase still progressing (300s)
[2022-12-14 19:32:03.132823] [0x00007f9f35dd96c0] [info]    Phase still progressing (600s)
[2022-12-14 19:37:03.132985] [0x00007f9f35dd96c0] [info]    Phase still progressing (900s)
[2022-12-14 19:42:03.133499] [0x00007f9f35dd96c0] [info]    Phase still progressing (1200s)
[2022-12-14 19:47:03.133714] [0x00007f9f35dd96c0] [info]    Phase still progressing (1500s)
[2022-12-14 19:52:03.134161] [0x00007f9f35dd96c0] [info]    Phase still progressing (1800s)
[2022-12-14 19:57:03.134760] [0x00007f9f35dd96c0] [info]    Phase still progressing (2100s)
[2022-12-14 20:02:03.135184] [0x00007f9f35dd96c0] [info]    Phase still progressing (2400s)
[2022-12-14 20:07:03.135379] [0x00007f9f35dd96c0] [info]    Phase still progressing (2700s)
[2022-12-14 20:12:03.135534] [0x00007f9f35dd96c0] [info]    Phase still progressing (3000s)
[2022-12-14 20:17:03.135798] [0x00007f9f35dd96c0] [info]    Phase still progressing (3300s)
[2022-12-14 20:22:03.135860] [0x00007f9f35dd96c0] [info]    Phase still progressing (3600s)
[2022-12-14 20:25:14.666080] [0x00007f9f33dd56c0] [info]    Ended phase 0
[2022-12-14 20:25:14.666483] [0x00007f9f355d86c0] [info]    Beginning phase 1
[2022-12-14 20:25:14.667752] [0x00007f9f35dd96c0] [info]    Phase still progressing (3791s)
[2022-12-14 20:25:26.295895] [0x00007f9f31dd16c0] [info]    Ended phase 1
[2022-12-14 20:25:26.296116] [0x00007f9f335d46c0] [info]    Beginning phase 2
[2022-12-14 20:25:26.296899] [0x00007f9f35dd96c0] [info]    Phase still progressing (3803s)
[2022-12-14 20:25:39.688442] [0x00007f9f315d06c0] [info]    Ended phase 2
[2022-12-14 20:25:39.688771] [0x00007f9f35dd96c0] [info]    Beginning phase 3
[2022-12-14 20:25:39.689600] [0x00007f9f35dd96c0] [info]    Phase still progressing (3816s)
[2022-12-14 20:30:39.689883] [0x00007f9f35dd96c0] [info]    Phase still progressing (4116s)
[2022-12-14 20:35:39.690392] [0x00007f9f35dd96c0] [info]    Phase still progressing (4416s)
[2022-12-14 20:38:39.665505] [0x00007f9f34dd76c0] [info]    Ended phase 3
[2022-12-14 20:38:39.666052] [0x00007f9f32dd36c0] [info]    Beginning phase 4
[2022-12-14 20:38:39.666877] [0x00007f9f35dd96c0] [info]    Phase still progressing (4596s)
[2022-12-14 20:38:52.656427] [0x00007f9f32dd36c0] [info]    Ended phase 4
{"t":{"$date":"2022-12-15T01:38:52.664Z"},"s":"I",  "c":"ASIO",     "id":6529201, "ctx":"shutdown","msg":"Network interface redundant shutdown","attr":{"state":"Stopped"}}
{"t":{"$date":"2022-12-15T01:38:52.665Z"},"s":"I",  "c":"ASIO",     "id":22582,   "ctx":"shutdown","msg":"Killing all outstanding egress activity."}
[curator] 2022/12/14 20:39:01 [p=info]: poplar rpc service terminated
(genny_venv) ➜  genny git:(frequency_map) ✗