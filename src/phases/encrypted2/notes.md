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