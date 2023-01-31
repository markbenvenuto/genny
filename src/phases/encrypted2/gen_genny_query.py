#!/usr/bin/env python3
import re
import math
import sys
import io
import argparse
import logging

import frequency_map

#######################################################
# GLOBAL CONSTANTS
#
# DOCUMENT_COUNT = 100000
# QUERY_COUNT = 10000

# Test Values
DOCUMENT_COUNT = 100
QUERY_COUNT = 10

EXPERIMENTS = [
  # {
  #   # Experiment Set q.1: Query unencrypted fields on unencrypted collection
  #   "name" : "es1",
  #   "coll" : "pbl",
  #   "encryptedFieldCount" : 0,
  #   "threadCounts" : [1,4,8,16],
  #   #"contentionFactors" : [1,4,8,16],
  #   "contentionFactors" : [1],
  #   "queries" : [
  #     {
  #       "field" : "fixed_10",
  #       "value" : "fixed_hf"
  #     },
  #     {
  #       "field" : "fixed_10",
  #       "value" : "uar"
  #     },
  #     {
  #       "field" : "uar_[1,10]",
  #       "value" : "uar"
  #     },
  #     {
  #       "field" : "uar_[1,10]",
  #       "value" : "uar_alllow"
  #     },
  #   ]
  # },
  {
    # Experiment Set q.2: Query unencrypted fields on partially encrypted collection
    "name" : "es2",
    "coll" : "pbl",
    "encryptedFieldCount" : 5,
    "threadCounts" : [1,4,8,16],
    "contentionFactors" : [1,4,8,16],
    "queries" : [
      {
        "field" : "fixed_10",
        "value" : "fixed_hf"
      },
      {
        "field" : "fixed_10",
        "value" : "uar"
      },
      {
        "field" : "uar_[6,10]",
        "value" : "uar"
      },
      {
        "field" : "uar_[6,10]",
        "value" : "uar_alllow"
      },
    ]
  },
  # {
  #   # Experiment Set q.3: Query encrypted fields on partially encrypted collection
  #   "name" : "es3",
  #   "coll" : "pbl",
  #   "encryptedFieldCount" : 5,
  #   "threadCounts" : [1,4,8,16],
  #   "contentionFactors" : [1,4,8,16],
  #   "queries" : [
  #     {
  #       "field" : "fixed_1",
  #       "value" : "fixed_hf"
  #     },
  #     {
  #       "field" : "fixed_1",
  #       "value" : "uar"
  #     },
  #     {
  #       "field" : "uar_[1,5]",
  #       "value" : "uar"
  #     },
  #     {
  #       "field" : "uar_[1,5]",
  #       "value" : "uar_alllow"
  #     },
  #   ]
  # },
  # {
  #   # Experiment Set q.4: Query encrypted fields on fully encrypted collection
  #   "name" : "es4",
  #   "coll" : "pbl",
  #   "encryptedFieldCount" : 10,
  #   "threadCounts" : [1,4,8,16],
  #   "contentionFactors" : [1,4,8,16],
  #   "queries" : [
  #     {
  #       "field" : "fixed_1",
  #       "value" : "fixed_hf"
  #     },
  #     {
  #       "field" : "fixed_1",
  #       "value" : "uar"
  #     },
  #     {
  #       "field" : "uar_[1,10]",
  #       "value" : "uar"
  #     },
  #     {
  #       "field" : "uar_[1,10]",
  #       "value" : "uar_alllow"
  #     },
  #   ]
  # },
  # {
  #   # Experiment Set q.5: Check the impact of BSON limit on queries on both encrypted and unencrypted fields
  #   "name" : "es5",
  #   "coll" : "blimit",
  #   "encryptedFieldCount" : 5,
  #   "threadCounts" : [1,4,8,16],
  #   "contentionFactors" : [1,4,8,16],
  #   "queries" : [
  #     {
  #       "field" : "fixed_1",
  #       "value" : "fixed_hf"
  #     },
  #     {
  #       "field" : "fixed_10",
  #       "value" : "fixed_hf"
  #     },
  #   ]
  # },
]



def transformFieldSelector(selector:str):
  """Convert a field selector in a query against a field or a set of fields"""
  # Fixed field
  if selector.startswith("fixed_"):
    return ["field" + selector.replace("fixed_", "")]

  if selector.startswith("uar_"):
    # print(selector)
    uar_re = r"uar_\[(\d),\s*(\d+)\]"
    m = re.match(uar_re, selector)
    # print(m)
    assert m is not None
    lower_bound = int(m[1])
    upper_bound = int(m[2])

    fields = []
    for i in range(lower_bound, upper_bound + 1):
      fields.append("field" + str(i))

    return fields

  raise NotImplemented()

def transformValueSelector(fb: frequency_map.FrequencyBuckets, selector:str):
  """Convert a value selector into a set of values to query"""

  if selector == "uar":
    return fb.uar()
  elif selector.startswith("fixed_"):
    return fb.fixed_bucket(selector.replace("fixed_", ""))
  elif selector.startswith("uar_alllow"):
    return fb.uar_all_low()

  raise NotImplemented()

class WorkloadWriter:
  """Write a workload to a string"""

  def __init__(self, testName, collectionName, queries, encryptedFields, contentionFactor, threadCount, do_load, do_query):
    self.testName = testName
    self.collectionName = f"{collectionName}_cf{contentionFactor}_ef{encryptedFields}"
    self.map_name = collectionName
    self.queries = queries
    self.encryptedFields = encryptedFields
    self.contentionFactor = contentionFactor
    self.threadCount = threadCount
    self.do_load = do_load
    self.do_query = do_query

    self.iterationsPerThread = math.floor(DOCUMENT_COUNT / self.threadCount)
    self.documentKey = f"document_insert_{self.map_name}"
    self.isEncrypted = encryptedFields > 0

    # TODO - stop hard coding this
    self.freq_map = frequency_map.load_map("src/phases/encrypted2/maps_pbl.yml")

    self.freq_buckets = {}
    for f in self.freq_map.keys():
      self.freq_buckets[f] = frequency_map.FrequencyBuckets(self.freq_map[f])

  def _generateFieldDescription(self):
    """Generate a description of encrypted fields for createCollection"""
    fieldDescription = ""

    for num in range(0, self.encryptedFields):
        if num == 0:
          fieldDescription += "    QueryableEncryptedFields:\n"
          fieldDescription += f'      field{num}: &field_schema {{ type: "string", queries: [{{queryType: "equality", contention: {self.contentionFactor}}}] }}\n'
          continue
        else:
          fieldDescription += f'      field{num}: *field_schema\n'

    return fieldDescription

  def _generateAutoRun(self):
      # return ""

      # # Tweak this bit to change tasks Genny will run in Evergreen
      # if ex["coll"] == "blimit" and enc == 5 and cf == 4 and tc == 4:
        return """AutoRun:
- When:
    mongodb_setup:
      $eq:
      - single-replica-fle
    branch_name:
      $neq:
      - v4.0
      - v4.2
      - v4.4
      - v5.0
      - v6.0
      - v6.1
      - v6.2"""
            # else:
            #   return ""

  def generate_query_operation(self, field, value):
    return f"""
      -
        OperationName: findOne
        OperationMetricsName: reads
        OperationCommand:
          Filter:
            {field} : {value}"""

  def generate_query_operations(self, query_selector):
    query_selector_block = ""

    count = 0
    for q in transformFieldSelector(query_selector["field"]):
      field_num = int(q.replace("field", ""))
      v = transformValueSelector(self.freq_buckets[field_num], query_selector["value"])

      # The uar generators return a list of values and we let Genny pick a random value at runtime via ^Choose
      if type(v) is list:
        v = "{ ^Choose: { from: %s }}" % (v)

      query_selector_block += self.generate_query_operation(q, v)
      count += 1

    return (count, query_selector_block)

  def generate_query_phase(self, name, query_selector):
    (count, operation_block) = self.generate_query_operations(query_selector)

    repeat_count = QUERY_COUNT / count / self.threadCount

    return f"""
  - Repeat: {repeat_count}
    Collection: *collection_param
    MetricsName: "{name}"
    Operations:
      {operation_block}"""

  def generate_query_phases(self):
    if not self.do_query:
      return ""

    phases = ""

    for (i, query_selector) in enumerate(self.queries):
      phases += self.generate_query_phase(f"q{i + 1}", query_selector)

    return phases

  def generate_logging_phases(self):
    phases = ""

    count = 3
    if self.do_query:
      count += len(self.queries)

    if self.do_load:
      count += 1

    for _ in range(count):
      phases += """
  - LogEvery: 5 minutes
    Blocking: None
    """

    return phases

  def generate_nop_phases(self):
    phases = ""

    count = 1
    if self.do_query:
      count += len(self.queries)

    if self.do_load:
      count += 1

    for _ in range(count):
      phases += """
  - *Nop
    """

    return phases

  def serialize(self):

    encryption_setup_block = f"""Encryption:
  UseCryptSharedLib: true
  CryptSharedLibPath: /data/workdir/mongocrypt/lib/mongo_crypt_v1.so
  EncryptedCollections:
  - Database: genny_qebench2
    Collection: {self.collectionName}
    EncryptionType: queryable
        """

    client_options = f"""
    EncryptionOptions:
      KeyVaultDatabase: "keyvault"
      KeyVaultCollection: "datakeys"
      EncryptedCollections:
      - genny_qebench2.{self.collectionName}
"""
    if self.isEncrypted == False:
        encryption_setup_block = "\n"
        client_options = "\n"

    load_phase = "- *load_phase"
    if not self.do_load:
      load_phase = ""

    query_phases = self.generate_query_phases()
    logging_phases = self.generate_logging_phases()
    nop_phases = self.generate_nop_phases()

    str_buf = io.StringIO("")

    str_buf.write(f"""SchemaVersion: 2018-07-01
Owner: "@10gen/server-security"
Description: |
  Performs a series of insert operations, using the following properties:
    - All documents have 11 fields, including 1 _id field, and 10 data fields.
    - The first {self.encryptedFields} data fields are encrypted.
    - _id is always unique.
    - Values in data fields fit a '{self.collectionName}' distribution. .
    - The insertions are performed by {self.threadCount} client threads.
  This test is uniquely identified as '{self.testName}'.

{encryption_setup_block}
{self._generateFieldDescription()}

Clients:
  EncryptedPool:
    QueryOptions:
      maxPoolSize: 400
{client_options}

##############################
########## pbl
map_pbl_f1: &map_pbl_f1
    id: map_pbl_f1
    from:
        v1: 9
        v2: 69
        v3: 151
        v4: 3629
        v5: 16720
        v6: 53720
        v7: 15609
        v8: 3910
        v9: 1723
        v10: 1016
        v11: 637
        v12: 436
        v13: 322
        v14: 239
        v15: 187
        v16: 145
        v17: 104
        v18: 116
        v19: 99
        v20: 84
        v21: 75
        v22: 64
        v23: 50
        v24: 46
        v25: 35
        v26: 32
        v27: 31
        v28: 38
        v29: 22
        v30: 36
        v31: 28
        v32: 24
        v33: 23
        v34: 24
        v35: 16
        v36: 15
        v37: 14
        v38: 14
        v39: 16
        v40: 15
        v41: 10
        v42: 10
        v43: 8
        v44: 11
        v45: 7
        v46: 8
        v47: 13
        v48: 5
        v49: 9
        v50: 6
        v51: 13
        v52: 7
        v53: 11
        v54: 10
        v55: 7
        v56: 8
        v57: 11
        v58: 7
        v59: 7
        v60: 4
        v61: 5
        v62: 3
        v63: 9
        v64: 5
        v65: 6
        v66: 5
        v67: 7
        v68: 1
        v69: 7
        v70: 6
        v71: 3
        v72: 3
        v73: 4
        v74: 4
        v75: 7
        v76: 1
        v77: 2
        v78: 1
        v79: 1
        v80: 4
        v81: 2
        v82: 2
        v83: 2
        v84: 3
        v85: 1
        v86: 2
        v87: 5
        v88: 1
        v89: 4
        v90: 2
        v91: 3
        v92: 4
        v93: 4
        v94: 1
        v95: 4
        v96: 3
        v97: 3
        v98: 1
        v99: 2
        v100: 3
        v101: 1
        v102: 3
        v103: 3
        v104: 1
        v105: 2
        v106: 1
        v107: 1
        v108: 3
        v109: 3
        v110: 3
        v111: 1
        v112: 1
        v113: 1
        v114: 2
        v115: 1
        v116: 1
        v117: 1
        v118: 1
        v119: 2
        v120: 1
        v121: 3
        v122: 1
        v123: 1
        v124: 1
        v125: 2
        v126: 1
        v127: 1
        v128: 1
        v129: 1
        v130: 1
        v131: 1
        v132: 1
        v133: 1
        v134: 1
        v135: 3
        v136: 1
        v137: 2
        v138: 1
        v139: 1
        v140: 1
        v141: 1
        v142: 1
        v143: 1
        v144: 1
        v145: 1
        v146: 1
        v147: 1
        v148: 1
        v149: 1
        v150: 1
        v151: 1
        v152: 1
        v153: 1
        v154: 1
        v155: 1
        v156: 1
        v157: 2
        v158: 2
        v159: 1
        v160: 1
        v161: 1
        v162: 2
        v163: 1
        v164: 1
        v165: 1
        v166: 2
        v167: 1
        v168: 1
        v169: 1
        v170: 1
        v171: 1
        v172: 1
        v173: 1
        v174: 1
        v175: 1
        v176: 1
        v177: 1
        v178: 1
        v179: 1
        v180: 1
        v181: 1
        v182: 1
        v183: 1
        v184: 1
        v185: 1
        v186: 1
        v187: 1
        v188: 1
        v189: 1
        v190: 1
        v191: 1
        v192: 1
        v193: 2
        v194: 1
        v195: 1
        v196: 1
        v197: 1
        v198: 1
        v199: 1
        v200: 1
        v201: 1
        v202: 1
        v203: 1
        v204: 1
        v205: 1
        v206: 1
        v207: 1
        v208: 1
        v209: 1
        v210: 1
        v211: 1
        v212: 1
        v213: 1
        v214: 1
        v215: 1
        v216: 1
        v217: 1
        v218: 1
        v219: 1
        v220: 1
        v221: 1
        v222: 1
        v223: 1
        v224: 1
        v225: 1

map_pbl_f2: &map_pbl_f2
    id: map_pbl_f2
    from:
        v1: 9
        v2: 69
        v3: 151
        v4: 3629
        v5: 16720
        v6: 53720
        v7: 15609
        v8: 3910
        v9: 1723
        v10: 1016
        v11: 637
        v12: 436
        v13: 322
        v14: 239
        v15: 187
        v16: 145
        v17: 104
        v18: 116
        v19: 99
        v20: 84
        v21: 75
        v22: 64
        v23: 50
        v24: 46
        v25: 35
        v26: 32
        v27: 31
        v28: 38
        v29: 22
        v30: 36
        v31: 28
        v32: 24
        v33: 23
        v34: 24
        v35: 16
        v36: 15
        v37: 14
        v38: 14
        v39: 16
        v40: 15
        v41: 10
        v42: 10
        v43: 8
        v44: 11
        v45: 7
        v46: 8
        v47: 13
        v48: 5
        v49: 9
        v50: 6
        v51: 13
        v52: 7
        v53: 11
        v54: 10
        v55: 7
        v56: 8
        v57: 11
        v58: 7
        v59: 7
        v60: 4
        v61: 5
        v62: 3
        v63: 9
        v64: 5
        v65: 6
        v66: 5
        v67: 7
        v68: 1
        v69: 7
        v70: 6
        v71: 3
        v72: 3
        v73: 4
        v74: 4
        v75: 7
        v76: 1
        v77: 2
        v78: 1
        v79: 1
        v80: 4
        v81: 2
        v82: 2
        v83: 2
        v84: 3
        v85: 1
        v86: 2
        v87: 5
        v88: 1
        v89: 4
        v90: 2
        v91: 3
        v92: 4
        v93: 4
        v94: 1
        v95: 4
        v96: 3
        v97: 3
        v98: 1
        v99: 2
        v100: 3
        v101: 1
        v102: 3
        v103: 3
        v104: 1
        v105: 2
        v106: 1
        v107: 1
        v108: 3
        v109: 3
        v110: 3
        v111: 1
        v112: 1
        v113: 1
        v114: 2
        v115: 1
        v116: 1
        v117: 1
        v118: 1
        v119: 2
        v120: 1
        v121: 3
        v122: 1
        v123: 1
        v124: 1
        v125: 2
        v126: 1
        v127: 1
        v128: 1
        v129: 1
        v130: 1
        v131: 1
        v132: 1
        v133: 1
        v134: 1
        v135: 3
        v136: 1
        v137: 2
        v138: 1
        v139: 1
        v140: 1
        v141: 1
        v142: 1
        v143: 1
        v144: 1
        v145: 1
        v146: 1
        v147: 1
        v148: 1
        v149: 1
        v150: 1
        v151: 1
        v152: 1
        v153: 1
        v154: 1
        v155: 1
        v156: 1
        v157: 2
        v158: 2
        v159: 1
        v160: 1
        v161: 1
        v162: 2
        v163: 1
        v164: 1
        v165: 1
        v166: 2
        v167: 1
        v168: 1
        v169: 1
        v170: 1
        v171: 1
        v172: 1
        v173: 1
        v174: 1
        v175: 1
        v176: 1
        v177: 1
        v178: 1
        v179: 1
        v180: 1
        v181: 1
        v182: 1
        v183: 1
        v184: 1
        v185: 1
        v186: 1
        v187: 1
        v188: 1
        v189: 1
        v190: 1
        v191: 1
        v192: 1
        v193: 2
        v194: 1
        v195: 1
        v196: 1
        v197: 1
        v198: 1
        v199: 1
        v200: 1
        v201: 1
        v202: 1
        v203: 1
        v204: 1
        v205: 1
        v206: 1
        v207: 1
        v208: 1
        v209: 1
        v210: 1
        v211: 1
        v212: 1
        v213: 1
        v214: 1
        v215: 1
        v216: 1
        v217: 1
        v218: 1
        v219: 1
        v220: 1
        v221: 1
        v222: 1
        v223: 1
        v224: 1
        v225: 1

map_pbl_f3: &map_pbl_f3
    id: map_pbl_f3
    from:
        v1: 9
        v2: 69
        v3: 151
        v4: 3629
        v5: 16720
        v6: 53720
        v7: 15609
        v8: 3910
        v9: 1723
        v10: 1016
        v11: 637
        v12: 436
        v13: 322
        v14: 239
        v15: 187
        v16: 145
        v17: 104
        v18: 116
        v19: 99
        v20: 84
        v21: 75
        v22: 64
        v23: 50
        v24: 46
        v25: 35
        v26: 32
        v27: 31
        v28: 38
        v29: 22
        v30: 36
        v31: 28
        v32: 24
        v33: 23
        v34: 24
        v35: 16
        v36: 15
        v37: 14
        v38: 14
        v39: 16
        v40: 15
        v41: 10
        v42: 10
        v43: 8
        v44: 11
        v45: 7
        v46: 8
        v47: 13
        v48: 5
        v49: 9
        v50: 6
        v51: 13
        v52: 7
        v53: 11
        v54: 10
        v55: 7
        v56: 8
        v57: 11
        v58: 7
        v59: 7
        v60: 4
        v61: 5
        v62: 3
        v63: 9
        v64: 5
        v65: 6
        v66: 5
        v67: 7
        v68: 1
        v69: 7
        v70: 6
        v71: 3
        v72: 3
        v73: 4
        v74: 4
        v75: 7
        v76: 1
        v77: 2
        v78: 1
        v79: 1
        v80: 4
        v81: 2
        v82: 2
        v83: 2
        v84: 3
        v85: 1
        v86: 2
        v87: 5
        v88: 1
        v89: 4
        v90: 2
        v91: 3
        v92: 4
        v93: 4
        v94: 1
        v95: 4
        v96: 3
        v97: 3
        v98: 1
        v99: 2
        v100: 3
        v101: 1
        v102: 3
        v103: 3
        v104: 1
        v105: 2
        v106: 1
        v107: 1
        v108: 3
        v109: 3
        v110: 3
        v111: 1
        v112: 1
        v113: 1
        v114: 2
        v115: 1
        v116: 1
        v117: 1
        v118: 1
        v119: 2
        v120: 1
        v121: 3
        v122: 1
        v123: 1
        v124: 1
        v125: 2
        v126: 1
        v127: 1
        v128: 1
        v129: 1
        v130: 1
        v131: 1
        v132: 1
        v133: 1
        v134: 1
        v135: 3
        v136: 1
        v137: 2
        v138: 1
        v139: 1
        v140: 1
        v141: 1
        v142: 1
        v143: 1
        v144: 1
        v145: 1
        v146: 1
        v147: 1
        v148: 1
        v149: 1
        v150: 1
        v151: 1
        v152: 1
        v153: 1
        v154: 1
        v155: 1
        v156: 1
        v157: 2
        v158: 2
        v159: 1
        v160: 1
        v161: 1
        v162: 2
        v163: 1
        v164: 1
        v165: 1
        v166: 2
        v167: 1
        v168: 1
        v169: 1
        v170: 1
        v171: 1
        v172: 1
        v173: 1
        v174: 1
        v175: 1
        v176: 1
        v177: 1
        v178: 1
        v179: 1
        v180: 1
        v181: 1
        v182: 1
        v183: 1
        v184: 1
        v185: 1
        v186: 1
        v187: 1
        v188: 1
        v189: 1
        v190: 1
        v191: 1
        v192: 1
        v193: 2
        v194: 1
        v195: 1
        v196: 1
        v197: 1
        v198: 1
        v199: 1
        v200: 1
        v201: 1
        v202: 1
        v203: 1
        v204: 1
        v205: 1
        v206: 1
        v207: 1
        v208: 1
        v209: 1
        v210: 1
        v211: 1
        v212: 1
        v213: 1
        v214: 1
        v215: 1
        v216: 1
        v217: 1
        v218: 1
        v219: 1
        v220: 1
        v221: 1
        v222: 1
        v223: 1
        v224: 1
        v225: 1

map_pbl_f4: &map_pbl_f4
    id: map_pbl_f4
    from:
        v1: 9
        v2: 69
        v3: 151
        v4: 3629
        v5: 16720
        v6: 53720
        v7: 15609
        v8: 3910
        v9: 1723
        v10: 1016
        v11: 637
        v12: 436
        v13: 322
        v14: 239
        v15: 187
        v16: 145
        v17: 104
        v18: 116
        v19: 99
        v20: 84
        v21: 75
        v22: 64
        v23: 50
        v24: 46
        v25: 35
        v26: 32
        v27: 31
        v28: 38
        v29: 22
        v30: 36
        v31: 28
        v32: 24
        v33: 23
        v34: 24
        v35: 16
        v36: 15
        v37: 14
        v38: 14
        v39: 16
        v40: 15
        v41: 10
        v42: 10
        v43: 8
        v44: 11
        v45: 7
        v46: 8
        v47: 13
        v48: 5
        v49: 9
        v50: 6
        v51: 13
        v52: 7
        v53: 11
        v54: 10
        v55: 7
        v56: 8
        v57: 11
        v58: 7
        v59: 7
        v60: 4
        v61: 5
        v62: 3
        v63: 9
        v64: 5
        v65: 6
        v66: 5
        v67: 7
        v68: 1
        v69: 7
        v70: 6
        v71: 3
        v72: 3
        v73: 4
        v74: 4
        v75: 7
        v76: 1
        v77: 2
        v78: 1
        v79: 1
        v80: 4
        v81: 2
        v82: 2
        v83: 2
        v84: 3
        v85: 1
        v86: 2
        v87: 5
        v88: 1
        v89: 4
        v90: 2
        v91: 3
        v92: 4
        v93: 4
        v94: 1
        v95: 4
        v96: 3
        v97: 3
        v98: 1
        v99: 2
        v100: 3
        v101: 1
        v102: 3
        v103: 3
        v104: 1
        v105: 2
        v106: 1
        v107: 1
        v108: 3
        v109: 3
        v110: 3
        v111: 1
        v112: 1
        v113: 1
        v114: 2
        v115: 1
        v116: 1
        v117: 1
        v118: 1
        v119: 2
        v120: 1
        v121: 3
        v122: 1
        v123: 1
        v124: 1
        v125: 2
        v126: 1
        v127: 1
        v128: 1
        v129: 1
        v130: 1
        v131: 1
        v132: 1
        v133: 1
        v134: 1
        v135: 3
        v136: 1
        v137: 2
        v138: 1
        v139: 1
        v140: 1
        v141: 1
        v142: 1
        v143: 1
        v144: 1
        v145: 1
        v146: 1
        v147: 1
        v148: 1
        v149: 1
        v150: 1
        v151: 1
        v152: 1
        v153: 1
        v154: 1
        v155: 1
        v156: 1
        v157: 2
        v158: 2
        v159: 1
        v160: 1
        v161: 1
        v162: 2
        v163: 1
        v164: 1
        v165: 1
        v166: 2
        v167: 1
        v168: 1
        v169: 1
        v170: 1
        v171: 1
        v172: 1
        v173: 1
        v174: 1
        v175: 1
        v176: 1
        v177: 1
        v178: 1
        v179: 1
        v180: 1
        v181: 1
        v182: 1
        v183: 1
        v184: 1
        v185: 1
        v186: 1
        v187: 1
        v188: 1
        v189: 1
        v190: 1
        v191: 1
        v192: 1
        v193: 2
        v194: 1
        v195: 1
        v196: 1
        v197: 1
        v198: 1
        v199: 1
        v200: 1
        v201: 1
        v202: 1
        v203: 1
        v204: 1
        v205: 1
        v206: 1
        v207: 1
        v208: 1
        v209: 1
        v210: 1
        v211: 1
        v212: 1
        v213: 1
        v214: 1
        v215: 1
        v216: 1
        v217: 1
        v218: 1
        v219: 1
        v220: 1
        v221: 1
        v222: 1
        v223: 1
        v224: 1
        v225: 1

map_pbl_f5: &map_pbl_f5
    id: map_pbl_f5
    from:
        v1: 9
        v2: 69
        v3: 151
        v4: 3629
        v5: 16720
        v6: 53720
        v7: 15609
        v8: 3910
        v9: 1723
        v10: 1016
        v11: 637
        v12: 436
        v13: 322
        v14: 239
        v15: 187
        v16: 145
        v17: 104
        v18: 116
        v19: 99
        v20: 84
        v21: 75
        v22: 64
        v23: 50
        v24: 46
        v25: 35
        v26: 32
        v27: 31
        v28: 38
        v29: 22
        v30: 36
        v31: 28
        v32: 24
        v33: 23
        v34: 24
        v35: 16
        v36: 15
        v37: 14
        v38: 14
        v39: 16
        v40: 15
        v41: 10
        v42: 10
        v43: 8
        v44: 11
        v45: 7
        v46: 8
        v47: 13
        v48: 5
        v49: 9
        v50: 6
        v51: 13
        v52: 7
        v53: 11
        v54: 10
        v55: 7
        v56: 8
        v57: 11
        v58: 7
        v59: 7
        v60: 4
        v61: 5
        v62: 3
        v63: 9
        v64: 5
        v65: 6
        v66: 5
        v67: 7
        v68: 1
        v69: 7
        v70: 6
        v71: 3
        v72: 3
        v73: 4
        v74: 4
        v75: 7
        v76: 1
        v77: 2
        v78: 1
        v79: 1
        v80: 4
        v81: 2
        v82: 2
        v83: 2
        v84: 3
        v85: 1
        v86: 2
        v87: 5
        v88: 1
        v89: 4
        v90: 2
        v91: 3
        v92: 4
        v93: 4
        v94: 1
        v95: 4
        v96: 3
        v97: 3
        v98: 1
        v99: 2
        v100: 3
        v101: 1
        v102: 3
        v103: 3
        v104: 1
        v105: 2
        v106: 1
        v107: 1
        v108: 3
        v109: 3
        v110: 3
        v111: 1
        v112: 1
        v113: 1
        v114: 2
        v115: 1
        v116: 1
        v117: 1
        v118: 1
        v119: 2
        v120: 1
        v121: 3
        v122: 1
        v123: 1
        v124: 1
        v125: 2
        v126: 1
        v127: 1
        v128: 1
        v129: 1
        v130: 1
        v131: 1
        v132: 1
        v133: 1
        v134: 1
        v135: 3
        v136: 1
        v137: 2
        v138: 1
        v139: 1
        v140: 1
        v141: 1
        v142: 1
        v143: 1
        v144: 1
        v145: 1
        v146: 1
        v147: 1
        v148: 1
        v149: 1
        v150: 1
        v151: 1
        v152: 1
        v153: 1
        v154: 1
        v155: 1
        v156: 1
        v157: 2
        v158: 2
        v159: 1
        v160: 1
        v161: 1
        v162: 2
        v163: 1
        v164: 1
        v165: 1
        v166: 2
        v167: 1
        v168: 1
        v169: 1
        v170: 1
        v171: 1
        v172: 1
        v173: 1
        v174: 1
        v175: 1
        v176: 1
        v177: 1
        v178: 1
        v179: 1
        v180: 1
        v181: 1
        v182: 1
        v183: 1
        v184: 1
        v185: 1
        v186: 1
        v187: 1
        v188: 1
        v189: 1
        v190: 1
        v191: 1
        v192: 1
        v193: 2
        v194: 1
        v195: 1
        v196: 1
        v197: 1
        v198: 1
        v199: 1
        v200: 1
        v201: 1
        v202: 1
        v203: 1
        v204: 1
        v205: 1
        v206: 1
        v207: 1
        v208: 1
        v209: 1
        v210: 1
        v211: 1
        v212: 1
        v213: 1
        v214: 1
        v215: 1
        v216: 1
        v217: 1
        v218: 1
        v219: 1
        v220: 1
        v221: 1
        v222: 1
        v223: 1
        v224: 1
        v225: 1

map_pbl_f6: &map_pbl_f6
    id: map_pbl_f6
    from:
        v1: 9
        v2: 69
        v3: 151
        v4: 3629
        v5: 16720
        v6: 53720
        v7: 15609
        v8: 3910
        v9: 1723
        v10: 1016
        v11: 637
        v12: 436
        v13: 322
        v14: 239
        v15: 187
        v16: 145
        v17: 104
        v18: 116
        v19: 99
        v20: 84
        v21: 75
        v22: 64
        v23: 50
        v24: 46
        v25: 35
        v26: 32
        v27: 31
        v28: 38
        v29: 22
        v30: 36
        v31: 28
        v32: 24
        v33: 23
        v34: 24
        v35: 16
        v36: 15
        v37: 14
        v38: 14
        v39: 16
        v40: 15
        v41: 10
        v42: 10
        v43: 8
        v44: 11
        v45: 7
        v46: 8
        v47: 13
        v48: 5
        v49: 9
        v50: 6
        v51: 13
        v52: 7
        v53: 11
        v54: 10
        v55: 7
        v56: 8
        v57: 11
        v58: 7
        v59: 7
        v60: 4
        v61: 5
        v62: 3
        v63: 9
        v64: 5
        v65: 6
        v66: 5
        v67: 7
        v68: 1
        v69: 7
        v70: 6
        v71: 3
        v72: 3
        v73: 4
        v74: 4
        v75: 7
        v76: 1
        v77: 2
        v78: 1
        v79: 1
        v80: 4
        v81: 2
        v82: 2
        v83: 2
        v84: 3
        v85: 1
        v86: 2
        v87: 5
        v88: 1
        v89: 4
        v90: 2
        v91: 3
        v92: 4
        v93: 4
        v94: 1
        v95: 4
        v96: 3
        v97: 3
        v98: 1
        v99: 2
        v100: 3
        v101: 1
        v102: 3
        v103: 3
        v104: 1
        v105: 2
        v106: 1
        v107: 1
        v108: 3
        v109: 3
        v110: 3
        v111: 1
        v112: 1
        v113: 1
        v114: 2
        v115: 1
        v116: 1
        v117: 1
        v118: 1
        v119: 2
        v120: 1
        v121: 3
        v122: 1
        v123: 1
        v124: 1
        v125: 2
        v126: 1
        v127: 1
        v128: 1
        v129: 1
        v130: 1
        v131: 1
        v132: 1
        v133: 1
        v134: 1
        v135: 3
        v136: 1
        v137: 2
        v138: 1
        v139: 1
        v140: 1
        v141: 1
        v142: 1
        v143: 1
        v144: 1
        v145: 1
        v146: 1
        v147: 1
        v148: 1
        v149: 1
        v150: 1
        v151: 1
        v152: 1
        v153: 1
        v154: 1
        v155: 1
        v156: 1
        v157: 2
        v158: 2
        v159: 1
        v160: 1
        v161: 1
        v162: 2
        v163: 1
        v164: 1
        v165: 1
        v166: 2
        v167: 1
        v168: 1
        v169: 1
        v170: 1
        v171: 1
        v172: 1
        v173: 1
        v174: 1
        v175: 1
        v176: 1
        v177: 1
        v178: 1
        v179: 1
        v180: 1
        v181: 1
        v182: 1
        v183: 1
        v184: 1
        v185: 1
        v186: 1
        v187: 1
        v188: 1
        v189: 1
        v190: 1
        v191: 1
        v192: 1
        v193: 2
        v194: 1
        v195: 1
        v196: 1
        v197: 1
        v198: 1
        v199: 1
        v200: 1
        v201: 1
        v202: 1
        v203: 1
        v204: 1
        v205: 1
        v206: 1
        v207: 1
        v208: 1
        v209: 1
        v210: 1
        v211: 1
        v212: 1
        v213: 1
        v214: 1
        v215: 1
        v216: 1
        v217: 1
        v218: 1
        v219: 1
        v220: 1
        v221: 1
        v222: 1
        v223: 1
        v224: 1
        v225: 1

map_pbl_f7: &map_pbl_f7
    id: map_pbl_f7
    from:
        v1: 9
        v2: 69
        v3: 151
        v4: 3629
        v5: 16720
        v6: 53720
        v7: 15609
        v8: 3910
        v9: 1723
        v10: 1016
        v11: 637
        v12: 436
        v13: 322
        v14: 239
        v15: 187
        v16: 145
        v17: 104
        v18: 116
        v19: 99
        v20: 84
        v21: 75
        v22: 64
        v23: 50
        v24: 46
        v25: 35
        v26: 32
        v27: 31
        v28: 38
        v29: 22
        v30: 36
        v31: 28
        v32: 24
        v33: 23
        v34: 24
        v35: 16
        v36: 15
        v37: 14
        v38: 14
        v39: 16
        v40: 15
        v41: 10
        v42: 10
        v43: 8
        v44: 11
        v45: 7
        v46: 8
        v47: 13
        v48: 5
        v49: 9
        v50: 6
        v51: 13
        v52: 7
        v53: 11
        v54: 10
        v55: 7
        v56: 8
        v57: 11
        v58: 7
        v59: 7
        v60: 4
        v61: 5
        v62: 3
        v63: 9
        v64: 5
        v65: 6
        v66: 5
        v67: 7
        v68: 1
        v69: 7
        v70: 6
        v71: 3
        v72: 3
        v73: 4
        v74: 4
        v75: 7
        v76: 1
        v77: 2
        v78: 1
        v79: 1
        v80: 4
        v81: 2
        v82: 2
        v83: 2
        v84: 3
        v85: 1
        v86: 2
        v87: 5
        v88: 1
        v89: 4
        v90: 2
        v91: 3
        v92: 4
        v93: 4
        v94: 1
        v95: 4
        v96: 3
        v97: 3
        v98: 1
        v99: 2
        v100: 3
        v101: 1
        v102: 3
        v103: 3
        v104: 1
        v105: 2
        v106: 1
        v107: 1
        v108: 3
        v109: 3
        v110: 3
        v111: 1
        v112: 1
        v113: 1
        v114: 2
        v115: 1
        v116: 1
        v117: 1
        v118: 1
        v119: 2
        v120: 1
        v121: 3
        v122: 1
        v123: 1
        v124: 1
        v125: 2
        v126: 1
        v127: 1
        v128: 1
        v129: 1
        v130: 1
        v131: 1
        v132: 1
        v133: 1
        v134: 1
        v135: 3
        v136: 1
        v137: 2
        v138: 1
        v139: 1
        v140: 1
        v141: 1
        v142: 1
        v143: 1
        v144: 1
        v145: 1
        v146: 1
        v147: 1
        v148: 1
        v149: 1
        v150: 1
        v151: 1
        v152: 1
        v153: 1
        v154: 1
        v155: 1
        v156: 1
        v157: 2
        v158: 2
        v159: 1
        v160: 1
        v161: 1
        v162: 2
        v163: 1
        v164: 1
        v165: 1
        v166: 2
        v167: 1
        v168: 1
        v169: 1
        v170: 1
        v171: 1
        v172: 1
        v173: 1
        v174: 1
        v175: 1
        v176: 1
        v177: 1
        v178: 1
        v179: 1
        v180: 1
        v181: 1
        v182: 1
        v183: 1
        v184: 1
        v185: 1
        v186: 1
        v187: 1
        v188: 1
        v189: 1
        v190: 1
        v191: 1
        v192: 1
        v193: 2
        v194: 1
        v195: 1
        v196: 1
        v197: 1
        v198: 1
        v199: 1
        v200: 1
        v201: 1
        v202: 1
        v203: 1
        v204: 1
        v205: 1
        v206: 1
        v207: 1
        v208: 1
        v209: 1
        v210: 1
        v211: 1
        v212: 1
        v213: 1
        v214: 1
        v215: 1
        v216: 1
        v217: 1
        v218: 1
        v219: 1
        v220: 1
        v221: 1
        v222: 1
        v223: 1
        v224: 1
        v225: 1

map_pbl_f8: &map_pbl_f8
    id: map_pbl_f8
    from:
        v1: 9
        v2: 69
        v3: 151
        v4: 3629
        v5: 16720
        v6: 53720
        v7: 15609
        v8: 3910
        v9: 1723
        v10: 1016
        v11: 637
        v12: 436
        v13: 322
        v14: 239
        v15: 187
        v16: 145
        v17: 104
        v18: 116
        v19: 99
        v20: 84
        v21: 75
        v22: 64
        v23: 50
        v24: 46
        v25: 35
        v26: 32
        v27: 31
        v28: 38
        v29: 22
        v30: 36
        v31: 28
        v32: 24
        v33: 23
        v34: 24
        v35: 16
        v36: 15
        v37: 14
        v38: 14
        v39: 16
        v40: 15
        v41: 10
        v42: 10
        v43: 8
        v44: 11
        v45: 7
        v46: 8
        v47: 13
        v48: 5
        v49: 9
        v50: 6
        v51: 13
        v52: 7
        v53: 11
        v54: 10
        v55: 7
        v56: 8
        v57: 11
        v58: 7
        v59: 7
        v60: 4
        v61: 5
        v62: 3
        v63: 9
        v64: 5
        v65: 6
        v66: 5
        v67: 7
        v68: 1
        v69: 7
        v70: 6
        v71: 3
        v72: 3
        v73: 4
        v74: 4
        v75: 7
        v76: 1
        v77: 2
        v78: 1
        v79: 1
        v80: 4
        v81: 2
        v82: 2
        v83: 2
        v84: 3
        v85: 1
        v86: 2
        v87: 5
        v88: 1
        v89: 4
        v90: 2
        v91: 3
        v92: 4
        v93: 4
        v94: 1
        v95: 4
        v96: 3
        v97: 3
        v98: 1
        v99: 2
        v100: 3
        v101: 1
        v102: 3
        v103: 3
        v104: 1
        v105: 2
        v106: 1
        v107: 1
        v108: 3
        v109: 3
        v110: 3
        v111: 1
        v112: 1
        v113: 1
        v114: 2
        v115: 1
        v116: 1
        v117: 1
        v118: 1
        v119: 2
        v120: 1
        v121: 3
        v122: 1
        v123: 1
        v124: 1
        v125: 2
        v126: 1
        v127: 1
        v128: 1
        v129: 1
        v130: 1
        v131: 1
        v132: 1
        v133: 1
        v134: 1
        v135: 3
        v136: 1
        v137: 2
        v138: 1
        v139: 1
        v140: 1
        v141: 1
        v142: 1
        v143: 1
        v144: 1
        v145: 1
        v146: 1
        v147: 1
        v148: 1
        v149: 1
        v150: 1
        v151: 1
        v152: 1
        v153: 1
        v154: 1
        v155: 1
        v156: 1
        v157: 2
        v158: 2
        v159: 1
        v160: 1
        v161: 1
        v162: 2
        v163: 1
        v164: 1
        v165: 1
        v166: 2
        v167: 1
        v168: 1
        v169: 1
        v170: 1
        v171: 1
        v172: 1
        v173: 1
        v174: 1
        v175: 1
        v176: 1
        v177: 1
        v178: 1
        v179: 1
        v180: 1
        v181: 1
        v182: 1
        v183: 1
        v184: 1
        v185: 1
        v186: 1
        v187: 1
        v188: 1
        v189: 1
        v190: 1
        v191: 1
        v192: 1
        v193: 2
        v194: 1
        v195: 1
        v196: 1
        v197: 1
        v198: 1
        v199: 1
        v200: 1
        v201: 1
        v202: 1
        v203: 1
        v204: 1
        v205: 1
        v206: 1
        v207: 1
        v208: 1
        v209: 1
        v210: 1
        v211: 1
        v212: 1
        v213: 1
        v214: 1
        v215: 1
        v216: 1
        v217: 1
        v218: 1
        v219: 1
        v220: 1
        v221: 1
        v222: 1
        v223: 1
        v224: 1
        v225: 1

map_pbl_f9: &map_pbl_f9
    id: map_pbl_f9
    from:
        v1: 9
        v2: 69
        v3: 151
        v4: 3629
        v5: 16720
        v6: 53720
        v7: 15609
        v8: 3910
        v9: 1723
        v10: 1016
        v11: 637
        v12: 436
        v13: 322
        v14: 239
        v15: 187
        v16: 145
        v17: 104
        v18: 116
        v19: 99
        v20: 84
        v21: 75
        v22: 64
        v23: 50
        v24: 46
        v25: 35
        v26: 32
        v27: 31
        v28: 38
        v29: 22
        v30: 36
        v31: 28
        v32: 24
        v33: 23
        v34: 24
        v35: 16
        v36: 15
        v37: 14
        v38: 14
        v39: 16
        v40: 15
        v41: 10
        v42: 10
        v43: 8
        v44: 11
        v45: 7
        v46: 8
        v47: 13
        v48: 5
        v49: 9
        v50: 6
        v51: 13
        v52: 7
        v53: 11
        v54: 10
        v55: 7
        v56: 8
        v57: 11
        v58: 7
        v59: 7
        v60: 4
        v61: 5
        v62: 3
        v63: 9
        v64: 5
        v65: 6
        v66: 5
        v67: 7
        v68: 1
        v69: 7
        v70: 6
        v71: 3
        v72: 3
        v73: 4
        v74: 4
        v75: 7
        v76: 1
        v77: 2
        v78: 1
        v79: 1
        v80: 4
        v81: 2
        v82: 2
        v83: 2
        v84: 3
        v85: 1
        v86: 2
        v87: 5
        v88: 1
        v89: 4
        v90: 2
        v91: 3
        v92: 4
        v93: 4
        v94: 1
        v95: 4
        v96: 3
        v97: 3
        v98: 1
        v99: 2
        v100: 3
        v101: 1
        v102: 3
        v103: 3
        v104: 1
        v105: 2
        v106: 1
        v107: 1
        v108: 3
        v109: 3
        v110: 3
        v111: 1
        v112: 1
        v113: 1
        v114: 2
        v115: 1
        v116: 1
        v117: 1
        v118: 1
        v119: 2
        v120: 1
        v121: 3
        v122: 1
        v123: 1
        v124: 1
        v125: 2
        v126: 1
        v127: 1
        v128: 1
        v129: 1
        v130: 1
        v131: 1
        v132: 1
        v133: 1
        v134: 1
        v135: 3
        v136: 1
        v137: 2
        v138: 1
        v139: 1
        v140: 1
        v141: 1
        v142: 1
        v143: 1
        v144: 1
        v145: 1
        v146: 1
        v147: 1
        v148: 1
        v149: 1
        v150: 1
        v151: 1
        v152: 1
        v153: 1
        v154: 1
        v155: 1
        v156: 1
        v157: 2
        v158: 2
        v159: 1
        v160: 1
        v161: 1
        v162: 2
        v163: 1
        v164: 1
        v165: 1
        v166: 2
        v167: 1
        v168: 1
        v169: 1
        v170: 1
        v171: 1
        v172: 1
        v173: 1
        v174: 1
        v175: 1
        v176: 1
        v177: 1
        v178: 1
        v179: 1
        v180: 1
        v181: 1
        v182: 1
        v183: 1
        v184: 1
        v185: 1
        v186: 1
        v187: 1
        v188: 1
        v189: 1
        v190: 1
        v191: 1
        v192: 1
        v193: 2
        v194: 1
        v195: 1
        v196: 1
        v197: 1
        v198: 1
        v199: 1
        v200: 1
        v201: 1
        v202: 1
        v203: 1
        v204: 1
        v205: 1
        v206: 1
        v207: 1
        v208: 1
        v209: 1
        v210: 1
        v211: 1
        v212: 1
        v213: 1
        v214: 1
        v215: 1
        v216: 1
        v217: 1
        v218: 1
        v219: 1
        v220: 1
        v221: 1
        v222: 1
        v223: 1
        v224: 1
        v225: 1

map_pbl_f10: &map_pbl_f10
    id: map_pbl_f10
    from:
        v1: 9
        v2: 69
        v3: 151
        v4: 3629
        v5: 16720
        v6: 53720
        v7: 15609
        v8: 3910
        v9: 1723
        v10: 1016
        v11: 637
        v12: 436
        v13: 322
        v14: 239
        v15: 187
        v16: 145
        v17: 104
        v18: 116
        v19: 99
        v20: 84
        v21: 75
        v22: 64
        v23: 50
        v24: 46
        v25: 35
        v26: 32
        v27: 31
        v28: 38
        v29: 22
        v30: 36
        v31: 28
        v32: 24
        v33: 23
        v34: 24
        v35: 16
        v36: 15
        v37: 14
        v38: 14
        v39: 16
        v40: 15
        v41: 10
        v42: 10
        v43: 8
        v44: 11
        v45: 7
        v46: 8
        v47: 13
        v48: 5
        v49: 9
        v50: 6
        v51: 13
        v52: 7
        v53: 11
        v54: 10
        v55: 7
        v56: 8
        v57: 11
        v58: 7
        v59: 7
        v60: 4
        v61: 5
        v62: 3
        v63: 9
        v64: 5
        v65: 6
        v66: 5
        v67: 7
        v68: 1
        v69: 7
        v70: 6
        v71: 3
        v72: 3
        v73: 4
        v74: 4
        v75: 7
        v76: 1
        v77: 2
        v78: 1
        v79: 1
        v80: 4
        v81: 2
        v82: 2
        v83: 2
        v84: 3
        v85: 1
        v86: 2
        v87: 5
        v88: 1
        v89: 4
        v90: 2
        v91: 3
        v92: 4
        v93: 4
        v94: 1
        v95: 4
        v96: 3
        v97: 3
        v98: 1
        v99: 2
        v100: 3
        v101: 1
        v102: 3
        v103: 3
        v104: 1
        v105: 2
        v106: 1
        v107: 1
        v108: 3
        v109: 3
        v110: 3
        v111: 1
        v112: 1
        v113: 1
        v114: 2
        v115: 1
        v116: 1
        v117: 1
        v118: 1
        v119: 2
        v120: 1
        v121: 3
        v122: 1
        v123: 1
        v124: 1
        v125: 2
        v126: 1
        v127: 1
        v128: 1
        v129: 1
        v130: 1
        v131: 1
        v132: 1
        v133: 1
        v134: 1
        v135: 3
        v136: 1
        v137: 2
        v138: 1
        v139: 1
        v140: 1
        v141: 1
        v142: 1
        v143: 1
        v144: 1
        v145: 1
        v146: 1
        v147: 1
        v148: 1
        v149: 1
        v150: 1
        v151: 1
        v152: 1
        v153: 1
        v154: 1
        v155: 1
        v156: 1
        v157: 2
        v158: 2
        v159: 1
        v160: 1
        v161: 1
        v162: 2
        v163: 1
        v164: 1
        v165: 1
        v166: 2
        v167: 1
        v168: 1
        v169: 1
        v170: 1
        v171: 1
        v172: 1
        v173: 1
        v174: 1
        v175: 1
        v176: 1
        v177: 1
        v178: 1
        v179: 1
        v180: 1
        v181: 1
        v182: 1
        v183: 1
        v184: 1
        v185: 1
        v186: 1
        v187: 1
        v188: 1
        v189: 1
        v190: 1
        v191: 1
        v192: 1
        v193: 2
        v194: 1
        v195: 1
        v196: 1
        v197: 1
        v198: 1
        v199: 1
        v200: 1
        v201: 1
        v202: 1
        v203: 1
        v204: 1
        v205: 1
        v206: 1
        v207: 1
        v208: 1
        v209: 1
        v210: 1
        v211: 1
        v212: 1
        v213: 1
        v214: 1
        v215: 1
        v216: 1
        v217: 1
        v218: 1
        v219: 1
        v220: 1
        v221: 1
        v222: 1
        v223: 1
        v224: 1
        v225: 1

LoadPhase: &load_phase
  Repeat: {self.iterationsPerThread}
  Collection: &collection_param {{^Parameter: {{Name: "Collection", Default: "{self.collectionName}"}}}}
  MetricsName: "load"
  Operations:
  - OperationName: withTransaction
    OperationCommand:
      Options:
        WriteConcern:
          Level: majority
          Journal: true
        ReadConcern:
          Level: snapshot
        ReadPreference:
          ReadMode: primaryPreferred
          MaxStaleness: 1000 seconds
      OperationsInTransaction:
      - OperationName: insertOne
        OperationMetricsName: inserts
        OperationCommand:
          OnSession: true
          Document:
            field1:  {{^TakeRandomStringFromFrequencyMapSingleton: *map_pbl_f1 }}
            field2:  {{^TakeRandomStringFromFrequencyMapSingleton: *map_pbl_f2 }}
            field3:  {{^TakeRandomStringFromFrequencyMapSingleton: *map_pbl_f3 }}
            field4:  {{^TakeRandomStringFromFrequencyMapSingleton: *map_pbl_f4 }}
            field5:  {{^TakeRandomStringFromFrequencyMapSingleton: *map_pbl_f5 }}
            field6:  {{^TakeRandomStringFromFrequencyMapSingleton: *map_pbl_f6 }}
            field7:  {{^TakeRandomStringFromFrequencyMapSingleton: *map_pbl_f7 }}
            field8:  {{^TakeRandomStringFromFrequencyMapSingleton: *map_pbl_f8 }}
            field9:  {{^TakeRandomStringFromFrequencyMapSingleton: *map_pbl_f9 }}
            field10:  {{^TakeRandomStringFromFrequencyMapSingleton: *map_pbl_f10 }}
            intField: {{^Inc: {{start: 0, step: 1, multiplier: {self.iterationsPerThread} }} }}

CreateUnencryptedIndexes: &create_index_phase

  Repeat: 1
  Database: genny_qebench2
  Collection: {self.collectionName}
  Operations:
  - OperationMetricsName: CreateUnencryptedIndexes
    OperationName: RunCommand
    OperationCommand:
      createIndexes: {self.collectionName}
      indexes:
      - key:
          intField: 1
        name: intFieldIndex


Actors:
- Name: InsertActor
  Type: CrudActor
  Threads: {self.threadCount}
  Database: genny_qebench2
  ClientName: EncryptedPool
  Phases:
  {load_phase}
  - &Nop {{Nop: true}}
  {query_phases}
  - Repeat: {self.iterationsPerThread}
    Collection: *collection_param
    MetricsName: "q5"
    Operations:

      -
        OperationName: findOne
        OperationMetricsName: reads
        OperationCommand:
          Filter:
            intField : {{$in : [33597, 38103, 82105, 44068, 54019, 18512, 56317, 70029, 66556, 1210, 12995, 94751, 87129, 4356, 748, 90067, 57115, 92133, 91743, 73316, 25957, 81524, 80536, 13282, 63985, 59518, 12603, 230, 23642, 26437, 19994, 28961, 54045, 35494, 57164, 46155, 65744, 57102, 54974, 25351, 82418, 72465, 73951, 84172, 17690, 53405, 3500, 67825, 66755, 62051, 25038, 96960, 54538, 2437, 84127, 12820, 59370, 12299, 84200, 34927, 13430, 26576, 34586, 99474, 74368, 56220, 84251, 31239, 37496, 7246, 70664, 36316, 29715, 53680, 8755, 34061, 14567, 93985, 23815, 14750, 34021, 9517, 92604, 57723, 93264, 77590, 75269, 56283, 64503, 52860, 91784, 29839, 38834, 34664, 45330, 30538, 28601, 95819, 77096, 97744, 1724, 95699, 44792, 24940, 92420, 75201, 54606, 10842, 82254, 56071, 30036, 99344, 66506, 23172, 21787, 41383, 7508, 65855, 67046, 31087, 93416, 19643, 95137, 74721, 22840, 32672, 73933, 16338, 60434, 61608, 86037, 12108, 45668, 60832, 71181, 43518, 9387, 48671, 68797, 37142, 4586, 41825, 41710, 85434, 63897, 71073, 23380, 23281, 32237, 47505, 77098, 98485, 32276, 60077, 80616, 49259, 42080, 59904, 75660, 65031, 94178, 88381, 29689, 68685, 65664, 15298, 79506, 62838, 33453, 20109, 37433, 47152, 62267, 80635, 7559, 32810, 87680, 881, 88135, 17433, 12785, 69062, 2737, 84974, 34789, 53122, 38853, 44868, 29666, 12561, 57463, 21462, 59020, 19707, 96888, 96443, 43668, 77628, 62713, 80597, 21226, 39568, 98109, 28231, 37034, 32176, 26689, 75213, 5351, 17964, 87704, 87901, 40956, 31188, 84422, 36536, 91217, 82089, 44543, 35692, 90064, 79253, 1912, 47898, 89270, 2243, 26263, 9846, 4476, 39825, 46871, 94109, 11626, 35150, 4443, 1070, 91271, 1271, 59684, 1887, 12761, 2018, 80453, 37945, 12672, 45014, 27689, 53268, 86336, 87120, 20070, 50852, 51059, 41319, 41407, 10714, 7190, 62980, 5992, 32750, 88039, 82676, 67745, 89750, 63908, 91208, 42523, 57573, 39335, 43308, 14059, 77758, 45962, 38946, 17768, 21862, 69488, 12372, 69871, 98497, 31061, 23459, 42221, 32296, 84166, 79517, 92922, 88422, 73989, 51011, 84656, 98124, 67091, 59862, 72296, 61822, 92086, 95438, 86880, 35296, 38526, 30429, 52911, 22776, 62536, 95635, 61993, 7588, 27720, 41967, 86242, 17474, 19821, 33697, 41301, 47356, 68427, 81752, 40597, 57041, 88546, 64529, 30639, 76051, 32489, 49035, 73714, 70218, 94791, 60786, 57997, 80840, 731, 98106, 65607, 93686, 20498, 13548, 3031, 89225, 86527, 89601, 94303, 28418, 97050, 81624, 50664, 47443, 51547, 71520, 34561, 82173, 22422, 26342, 15458, 8355, 33838, 35947, 69803, 13779, 61452, 51349, 30552, 67955, 36346, 6200, 80042, 87892, 69476, 59576, 61229, 70450, 30647, 3756, 9063, 23104, 87583, 65520, 76125, 96015, 94093, 92284, 5899, 26140, 83834, 48397, 65090, 10048, 16803, 47807, 83915, 10607, 67931, 10831, 88544, 9669, 11853, 13953, 96335, 51670, 81273, 30704, 23165, 56463, 20309, 81325, 57239, 62498, 85641, 71466, 16355, 8064, 24393, 49681, 90507, 13697, 91165, 69879, 47630, 18555, 42499, 55007, 69595, 94355, 95260, 718, 66120, 19355, 17484, 5641, 74952, 42130, 48049, 22409, 34052, 41101, 96792, 37047, 23408, 45020, 66844, 73798, 35426, 53564, 30662, 63313, 38845, 6000, 78109, 80775, 75462, 97658, 66765, 17180, 19231, 43539, 47340, 78223, 98300, 38755, 6243, 31366, 63621, 58811, 11554, 21625, 70080, 68561, 51793, 25345, 77489, 24451, 71510, 25128, 14269, 35896, 21424, 53821, 38183, 56543, 70484, 15726, 58178, 1472, 76113, 10509, 75029, 8222, 50345, 56837, 50903, 71050, 62246, 13445, 31046, 50072, 42060, 83613, 65725, 79739, 23532, 80541, 40605, 9808, 11432, 92178, 59977, 85438, 95441, 19969, 97056, 16860, 1114, 38021, 84497, 86425, 35106, 76777, 31022, 57724, 87020, 74001, 71151, 22471, 13272, 89612, 87416, 37284, 7755, 77215, 98287, 64134, 35400, 69339, 10965, 11356, 7102, 19515, 13363, 1316, 81578, 1599, 50104, 81160, 71503, 10687, 35981, 1192, 68711, 40895, 99848, 12123, 37166, 71564, 91398, 17379, 49295, 13078, 51440, 65113, 53590, 90709, 45181, 87478, 50047, 76602, 12510, 85224, 79726, 29135, 48800, 33188, 98196, 12465, 73839, 40183, 61643, 7144, 79304, 84723, 13864, 60777, 89460, 28904, 95057, 89827, 33406, 29580, 70270, 52801, 59210, 51834, 63794, 4453, 55626, 35890, 86842, 71045, 93496, 8993, 49510, 51253, 14215, 31679, 13221, 16397, 48857, 44314, 8150, 49515, 4519, 68193, 42821, 56408, 32109, 26785, 90083, 78947, 85103, 3073, 53698, 644, 76190, 70192, 13041, 77467, 11788, 25956, 7361, 44620, 43065, 94864, 74934, 90823, 61915, 31943, 74211, 88780, 48659, 76312, 7942, 37509, 40125, 89595, 10646, 4119, 47126, 98551, 2428, 77652, 32883, 21340, 20395, 19886, 10075, 80560, 2028, 37227, 60756, 31417, 51407, 73472, 31614, 64677, 63566, 70504, 92024, 54004, 28504, 90732, 77151, 83810, 49591, 66504, 49332, 44121, 13962, 51352, 76606, 94988, 74843, 84489, 47772, 53945, 93448, 81798, 7012, 46204, 61480, 91521, 26070, 77775, 29042, 54154, 20166, 20503, 93603, 621, 28362, 43523, 54899, 17581, 15286, 62826, 89174, 64327, 65367, 8287, 77803, 8300, 76499, 90647, 62861, 28739, 26940, 88302, 83816, 47277, 85079, 89250, 27480, 74548, 68238, 37316, 93169, 36879, 64153, 62678, 94693, 5538, 78046, 38994, 29961, 67514, 26226, 69442, 25099, 55844, 68357, 43502, 19121, 76009, 97590, 47784, 8643, 81987, 24506, 68814, 89172, 61579, 16335, 5562, 31202, 24938, 1860, 73727, 25524, 40974, 68713, 48354, 54303, 38617, 82975, 99711, 81602, 49513, 38217, 9077, 35975, 53043, 51119, 56988, 57855, 22107, 18948, 75162, 75643, 89347, 65341, 91534, 35125, 71222, 43566, 70802, 56656, 16179, 16478, 18952, 41218, 22904, 76267, 58543, 77801, 14915, 6194, 49842, 20532, 15818, 18774, 61870, 9589, 325, 31383, 23151, 11861, 26509, 73281, 23108, 14203, 64922, 52805, 7795, 52802, 21101, 47991, 70684, 27856, 94813, 1412, 44147, 90638, 71217, 43007, 93338, 91186, 71861, 58981, 97617, 59974, 86352, 71327, 97672, 34202, 99925, 6736, 61286, 56352, 88830, 90476, 91535, 40925, 74378, 96261, 359, 41661, 16996, 25911, 21773, 46200, 78367, 19069, 28193, 5897, 34793, 78744, 83711, 41119, 968, 49678, 59901, 13582, 61185, 45815, 97028, 79764, 63557, 83992, 61705, 80492, 39243, 7578, 43043, 21528, 15445, 50935, 10590, 68453, 43106, 99218, 23749, 25055, 61405, 27244, 64736, 99691, 44409, 20189, 9699, 63660, 77956, 26897, 33704, 86397, 62093, 91317, 77265, 43824, 13100, 76170, 65776, 82025, 93818, 37379, 14202, 39995, 65974, 20536, 60695, 80312, 82293, 76703, 70965, 32643, 17600, 54285, 35439, 67567, 97655, 26404, 55954, 33905, 65618, 65116, 30996, 79098, 90840, 41909, 31433, 29513, 20175, 97111, 65362, 76541, 10880, 7887, 96328, 89645, 8604, 11500, 26926, 92159, 61691, 70006, 84493, 79236, 75496, 44910, 91932, 82529, 77992, 24024, 75892, 69345, 84753, 40409, 31931, 46342, 49987, 73341, 13724, 39309, 15068, 73288, 54746, 47520, 7335, 96693, 16797, 47155, 80558, 73332, 74084, 47592, 3292, 82605, 98117, 83696, 84767, 96978, 17302, 554, 72056, 4365, 68925, 59726, 85866, 28230, 33806, 81662, 27723, 98880, 50803, 36858, 55912, 28066, 10722, 85169, 71679, 61894, 45221, 39239, 34499, 26844, 54074, 53641, 96613, 70077, 30884, 41880, 78220, 13286, 9226, 42173, 79900, 62837, 52569, 55600, 912, 61417, 3319, 10944, 27517, 94678, 86059, 82012, 43326, 53646, 58775, 96084, 95766, 62358, 3926, 91188, 61512, 37729, 62825, 78444, 72086, 62954, 4173, 61115, 41552, 10680, 32628, 54931, 26665, 34755, 39669, 81074, 26153, 22651, 43936, 33407, 21083, 45335, 22880, 58572, 66894, 50271, 77328, 64180, 31866, 76314, 99493, 95566, 91653, 85653, 93266, 25699, 46274, 3458, 26402, 24576, 15730, 25224, 85646, 80980, 69088, 45481, 81658, 59258, 82835, 38582, 3414, 91170, 25020, 40418, 92042, 12073, 59155, 40399, 51598, 84180, 37828, 92615, 58463, 5204, 84150, 47803, 26478, 84213, 68267, 25716, 19373, 81461, 97257, 59730, 44077, 3108, 68333, 51826, 15136, 11270, 96996, 13674, 89966, 23976, 84260, 36774, 53853, 61460, 56120, 36577, 78911, 60530, 67576, 78353, 95309, 1284, 14212, 55604, 77650, 93673, 89723, 84795, 57221, 60441, 5609, 1110, 62171, 73262, 94871, 40132, 41432, 95423, 13873, 60372, 33684, 58578, 14326, 36434, 88744, 6388, 1003, 92901, 56747, 81324, 71398, 93467, 48126, 97973, 65419, 62392, 16988, 57300, 35540, 17502, 29981, 48666, 85085, 29705, 8262, 35721, 31762, 26053, 4099, 49359, 82152, 14997, 58786, 89183, 56833, 99269, 81408, 52245, 56087, 72920, 67306, 25297, 22266, 39226, 57581, 20184, 72456, 32742, 99646, 44490, 62369, 67799, 59196, 80296, 71839, 21965, 41695, 51246, 74355, 37004, 16640, 21535, 67423, 39228, 90018, 8399, 31925, 70400, 43869, 21191, 85140, 83877, 25071, 42158, 84748, 52147, 61123, 86314, 10684, 36644, 28420, 37070, 73074, 61752, 16927, 47647, 69863, 16268, 82439, 92005, 28329, 95305, 25707, 25170, 17624, 95402, 36420, 74694, 87225, 76762, 77174, 91786, 76666, 16302, 21738, 27001, 92817, 29036, 60512, 97171, 45626, 75899, 91623, 53844, 50286, 27261, 84324, 56138, 21821, 70748, 79744, 70205, 47460, 66289, 3788, 23935, 47631, 11418, 3917, 65871, 35061, 10989, 95120, 54413, 57814, 73344, 8239, 1692, 46907, 3233, 92324, 6033, 79884, 44613, 36521, 87670, 60613, 70698, 3972, 29899, 68133, 36083, 62732, 9044, 49033, 99733, 6426, 55361, 57355, 38185, 2882, 88928, 57805, 89779, 35359, 62245, 59766, 20689, 54464, 15658, 20067, 55854, 5437, 83993, 57283, 80651, 13331, 3390, 97535, 7511, 93819, 72488, 28657, 4089, 63372, 2755, 71712, 36853, 43265, 81852, 76456, 11877, 10948, 74015, 40844, 10189, 71196, 35353, 34984, 84087, 69173, 28708, 89943, 40164, 59188, 43826, 17646, 29731, 4382, 78699, 22043, 10806, 26797, 72841, 81087, 68335, 95147, 93085, 90960, 96297, 23781, 93541, 66165, 27197, 64846, 88838, 56451, 58512, 73736, 4304, 39745, 22339, 74544, 28931, 90566, 31635, 53766, 25124, 4976, 31269, 10845, 71871, 24443, 94225, 49726, 21444, 63423, 76248, 33423, 56298, 64257, 33573, 88273, 45405, 52372, 41126, 91799, 75212, 84349, 24597, 85961, 55213, 53181, 33865, 39225, 1150, 24204, 42492, 23113, 23497, 80938, 54699, 46976, 19542, 22735, 24369, 5772, 29665, 17092, 41919, 18005, 47330, 92366, 31448, 45639, 34602, 15958, 54259, 71822, 21664, 95698, 49362, 71591, 33766, 16851, 35605, 7654, 20063, 91089, 42116, 97228, 78249, 10895, 64378, 17131, 7145, 93043, 24625, 46572, 60236, 43416, 51956, 21973, 83687, 83515, 40443, 32373, 19281, 47830, 60225, 26965, 82388, 82257, 48223, 86511, 39891, 15728, 44761, 90811, 46597, 79450, 63280, 51166, 42872, 32030, 33678, 65234, 92450, 47272, 38865, 5219, 58281, 64042, 62596, 61335, 87904, 30897, 56049, 72109, 38271, 93186, 93866, 56276, 55018, 61517, 40872, 85722, 84038, 56117, 52788, 67226, 96877, 71333, 42037, 31362, 27054, 4486, 61523, 35433, 33143, 47432, 85365, 5138, 8899, 94131, 38995, 66904, 4132, 97766, 79259, 92188, 31780, 87052, 46708, 88655, 63982, 90192, 72467, 89345, 34368, 9137, 47665, 93758, 51783, 69155, 96866, 55906, 66339, 4700, 90323, 10027, 71888, 38002, 25968, 25740, 93206, 50166, 6097, 27912, 2175, 18284, 66970, 65605, 95439, 14878, 2276, 21884, 20925, 44602, 44950, 24780, 4111, 90893, 52573, 56479, 27974, 96304, 51725, 30241, 67475, 35237, 62705, 9238, 38971, 69946, 23163, 61708, 32800, 2011, 68099, 22773, 75274, 7522, 40005, 71346, 11362, 66480, 61284, 38237, 16957, 6187, 20679, 82489, 42340, 83224, 57941, 83458, 50255, 76484, 42242, 56053, 89547, 4957, 27165, 73516, 92979, 80252, 87883, 7295, 3064, 48189, 87515, 5092, 92618, 58994, 73996, 10458, 85766, 63082, 51025, 59933, 89858, 17819, 37687, 70679, 35920, 91513, 56372, 79524, 35022, 17161, 86046, 33472, 5123, 17435, 75733, 3906, 73079, 94518, 57656, 90355, 69094, 27338, 61038, 44978, 93935, 79616, 77688, 77480, 93911, 3678, 56955, 66541, 37743, 30962, 10792, 85795, 40435, 92815, 91621, 80762, 48846, 71403, 5635, 65161, 16313, 10565, 32442, 15550, 93828, 87953, 83492, 7206, 54889, 39534, 34896, 86952, 32273, 63080, 55557, 84739, 29695, 26016, 81862, 46023, 67894, 30682, 65202, 92466, 16810, 59547, 90245, 41936, 84192, 87676, 39896, 76055, 37659, 76198, 35377, 36731, 28165, 12274, 72237, 95465, 58836, 13652, 74600, 49393, 98421, 32689, 48805, 32694, 20167, 23604, 57976, 7929, 55801, 15521, 10426, 31994, 19124, 89997, 22618, 42386, 4027, 41208, 10407, 59557, 68443, 98516, 53894, 53924, 20019, 94793, 62064, 26398, 62180, 80913, 28303, 58442, 98380, 1941, 50237, 90927, 95529, 82674, 22827, 11873, 21764, 93026, 64641, 27444, 37588, 42690, 73099, 48868, 22412, 15688, 64667, 46942, 81045, 7271, 93080, 55445, 49914, 4387, 63362, 83604, 99014, 82299, 98670, 88796, 32381, 11379, 12402, 55085, 54534, 61553, 61408, 77704, 24676, 16040, 7106, 32667, 57094, 21490, 80890, 57931, 90242, 77363, 15021, 92068, 31312, 5649, 25026, 87657, 8321, 445, 86283, 81444, 99565, 64200, 72536, 68802, 11846, 99908, 4607, 41700, 2218, 99288, 74632, 11988, 26903, 68290, 93076, 11794, 14506, 56877, 3303, 28425, 83395, 3196, 76953, 16715, 70653, 73818, 18560, 30608, 28660, 21303, 30491, 17636, 33243, 15786, 15092, 2818, 78251, 42958, 96018, 19959, 11279, 51892, 40554, 13579, 96158, 11947, 71309, 14930, 35415, 26766, 45359, 48793, 92713, 32762, 30287, 26587, 4779, 62672, 89349, 10459, 23877, 57900, 38661, 26303, 35093, 50276, 19940, 86140, 48210, 6231, 49539, 64183, 5981, 11099, 90079, 70689, 96916, 60320, 60850, 90361, 87975, 5606, 47099, 29697, 69715, 59274, 65841, 36338, 23730, 81209, 7239, 68018, 48045, 47717, 2328, 20943, 17972, 6874, 88632, 11217, 41271, 52354, 2152, 1234, 47626, 46252, 34464, 77442, 50194, 18083, 58663, 96256, 59213, 7146, 76775, 49140, 27316, 71561, 4142, 45122, 99178, 87987, 64401, 15474, 77766, 23070, 82431, 25157, 2229, 44145, 34978, 95282, 37090, 2825, 80131, 28257, 57482, 12238, 59689, 99211, 56758, 40419, 79387, 54915, 80888, 25581, 6559, 59350, 52499, 72039, 37406, 60476, 29059, 87662, 98227, 7641, 82504, 88850, 9261, 6781, 79017, 98875, 82759, 40212, 80880, 74323, 49345, 76487, 20086, 31246, 90716, 54575, 96082, 1872, 65818, 30336, 79532, 63164, 86670, 35346, 79324, 89249, 48366, 63957, 20586, 55658, 64775, 87427, 88492, 90094, 50043, 89459, 75712, 60940, 16556, 4187, 17929, 51298, 25163, 93564, 52112, 79605, 98414, 59566, 3092, 82374, 26533, 4775, 46087, 41990, 61554, 14148, 51970, 88953, 17298, 4499, 32490, 35107, 15278, 61832, 26703, 89721, 94271, 33241, 81804, 82639, 20398, 63212, 26486, 81632, 46363, 26945, 84593, 52301, 67396, 92045, 53056, 88115, 92866, 31728, 28365, 96377, 92389, 93301, 88326, 5535, 33090, 43555, 65608, 35238, 36639, 58799, 46337, 82843, 9902, 68373, 54426, 11406, 27582, 99417, 73051, 23073, 36340, 71343, 3312, 44136, 18040, 24261, 26255, 15145, 97989, 16953, 45550, 74392, 73928, 77666, 86211, 86963, 51607, 14683, 79622, 6301, 52156, 74793, 12854, 69292, 58331, 80710, 18349, 80904, 68309, 81128, 24746, 12511, 19981, 82852, 99953, 19440, 40611, 97983, 23309, 55962, 69685, 67000, 53781, 22104, 94194, 90860, 87848, 13551, 64425, 14223, 6883, 94932, 5664, 65743, 80493, 25527, 17516, 46408, 78296, 25142, 2335, 32813, 22323, 24018, 11409, 12428, 90032, 37264, 76251, 18333, 55457, 38436, 58024, 18290, 78858, 71179, 44157, 76523, 28100, 38438, 3655, 53390, 10385, 95634, 26096, 41076, 71183, 39074, 66489, 61076, 17428, 69010, 60251, 67210, 67186, 70390, 31817, 29820, 56714, 82546, 61334, 20649, 63135, 67827, 35663, 97509, 1100, 800, 51436, 40961, 88781, 38680, 94319, 55782, 81905, 75151, 34406, 4651, 30100, 60025, 23088, 67158, 67635, 1249, 8809, 36288, 9740, 63565, 8479, 61310, 96912, 5413, 39266, 88962, 15840, 95285, 33774, 51662, 50316, 11222, 18287, 46604, 67563, 92239, 78554, 30806, 59717, 33220, 19070, 64942, 29283, 47516, 59665, 23992, 80700, 95862, 21605, 60871, 17992, 5842, 66269, 34812, 14272, 69645, 99487, 96341, 73240, 44360, 57575, 19477, 21874, 60663, 77913, 84500, 82102, 46256, 60275, 11342, 35634, 46616, 94036, 46112, 77283, 17971, 45372, 5192, 10802, 19551, 8467, 38195, 85189, 27548, 88083, 812, 77454, 37737, 66175, 13448, 20883, 64537, 35576, 3868, 5952, 69936, 91824, 74860, 25453, 8216, 90251, 20112, 33085, 74031, 9162, 17056, 95284, 6234, 45255, 68183, 79862, 77316, 90191, 49898, 58755, 59367, 20981, 16476, 2717, 43966, 13825, 91620, 87824, 59241, 53611, 4823, 31469, 59287, 81783, 89015, 50324, 96228, 34486, 24913, 95972, 66441, 90336, 1875, 85742, 59263, 97398, 47534, 31029, 43234, 42881, 57611, 15097, 77421, 1625, 99578, 81223, 19526, 64046, 64394, 40373, 67101, 85286, 26832, 30407, 59097, 85092, 30122, 50719, 14943, 45889, 13596, 45189, 27485, 11309, 13166, 76848, 58713, 44534, 2477, 92765, 88337, 81041, 1088, 49155, 81604, 22008, 53290, 71436, 54828, 43406, 15827, 27602, 87934, 42894, 16148, 20825, 10805, 2242, 6573, 35059, 87859, 33764, 65457, 77869, 25241, 65667, 12947, 61137, 23648, 22355, 34890, 48131, 29200, 61733, 5721, 45019, 46415, 53508, 49174, 78860, 75170, 49821, 6364, 26087, 31330, 85385, 32984, 35585, 92370, 73787, 25420, 71673, 65942, 94642, 32553, 13397, 51296, 49950, 28565, 75351, 20866, 20376, 21532, 93521, 4683, 62703, 26470, 16229, 61644, 72193, 31420, 23839, 10780, 70326, 94215, 53361, 89377, 70606, 94469, 9288, 41149, 91496, 4378, 5358, 90142, 25261, 92632, 26506, 53913, 2502, 67853, 69880, 31077, 29758, 36865, 9860, 38479, 12757, 24156, 68617, 95535, 88248, 16423, 29881, 22247, 32352, 79305, 77041, 97190, 79234, 72957, 43607, 82704, 7666, 64304, 36478, 42836, 4149, 89228, 19095, 89679, 86566, 16506, 331, 75970, 21784, 63241, 52608, 21684, 63740, 83938, 26040, 98430, 43438, 13035, 55877, 15673, 63298, 8140, 93529, 25974, 91902, 35742, 66932, 37280, 67920, 76384, 5751, 19205, 60727, 36835, 46285, 24920, 96703, 98812, 8484, 55037, 82079, 45452, 39617, 29082, 80865, 64355, 57561, 29170, 58053, 68525, 98481, 6381, 22496, 6508, 46736, 15614, 72619, 4656, 98229, 8236, 35245, 57223, 25192, 11369, 45939, 91441, 24218, 43968, 4424, 87805, 28584, 73620, 81008, 37457, 71234, 80485, 9216, 33072, 64904, 86960, 74305, 99849, 48106, 77313, 96749, 30049, 29807, 72259, 97688, 19346, 91851, 87659, 16398, 45209, 81147, 4693, 47265, 94785, 32991, 31132, 58464, 40734, 36922, 57588, 84821, 92459, 81198, 57508, 915, 10164, 27035, 9293, 40937, 46048, 38823, 19292, 44707, 79738, 62331, 94449, 91606, 14942, 45601, 44640, 92965, 81690, 67498, 70448, 89481, 82565, 37649, 72201, 46109, 6290, 87835, 42066, 16036, 60820, 71717, 93962, 36846, 90777, 5922, 29882, 14923, 61279, 62310, 59745, 27529, 93684, 16807, 93226, 8924, 59509, 59428, 14037, 98047, 52657, 72759, 2193, 89082, 78149, 18647, 92732, 47024, 34576, 43102, 78696, 67360, 86883, 42641, 58403, 33389, 83460, 34546, 49493, 99422, 18675, 24351, 8799, 82359, 75635, 88420, 11121, 55853, 52732, 17619, 58398, 23572, 133, 72624, 5850, 76417, 59081, 39983, 53160, 1065, 12966, 33783, 66317, 5367, 99967, 58409, 6477, 79812, 6712, 50490, 62537, 3268, 69661, 38801, 4947, 57863, 45226, 98179, 74568, 95991, 2898, 3111, 39086, 56841, 24285, 62065, 85524, 25728, 90568, 56498, 89730, 71033, 68717, 82149, 57105, 40932, 77543, 15203, 50555, 58719, 10077, 79222, 91394, 96124, 59021, 91021, 12509, 54390, 53939, 26922, 51757, 98688, 43079, 52677, 17792, 74665, 49858, 44367, 66647, 11047, 6248, 92625, 72651, 2316, 19323, 82471, 87972, 15210, 75743, 84562, 80659, 35881, 5680, 61883, 89761, 11722, 82517, 51030, 64929, 35636, 78234, 99889, 16711, 85452, 32600, 59541, 80281, 45875, 1099, 57710, 59996, 61438, 49202, 2310, 65993, 67465, 77606, 40978, 74219, 25002, 98029, 48726, 17686, 56939, 37970, 38034, 10932, 57854, 48395, 16448, 51916, 72699, 42302, 7652, 19517, 61018, 37221, 48232, 42788, 26068, 67611, 47072, 3201, 95843, 82875, 11655, 94162, 4074, 18873, 44655, 49752, 32006, 1146, 5964, 83599, 74187, 98588, 71470, 60050, 1297, 90401, 92837, 84458, 32217, 52784, 28635, 57001, 34901, 58822, 37876, 60277, 54539, 71920, 50026, 85583, 62524, 37839, 88031, 97224, 65632, 19744, 54969, 91133, 32182, 6752, 62416, 81644, 78882, 60045, 17159, 74192, 70040, 90605, 85010, 39416, 61927, 37540, 1574, 25918, 83989, 72843, 34795, 50583, 83013, 43035, 76409, 17217, 17935, 89341, 65975, 47208, 39399, 74778, 25442, 94664, 20336, 45935, 31844, 59481, 27265, 6277, 55549, 54204, 6405, 18648, 45977, 23064, 91679, 21463, 62493, 37050, 28339, 71571, 89094, 93594, 7631, 95901, 17707, 35322, 55562, 57331, 44955, 67078, 73126, 22571, 82860, 37405, 90282, 89881, 81350, 12906, 40199, 87786, 61824, 29500, 18579, 49544, 34942, 44437, 4467, 98447, 30450, 44228, 55311, 11772, 25998, 81951, 21366, 69785, 80436, 45942, 95627, 17890, 84377, 5714, 73031, 36775, 64749, 62598, 61264, 37281, 67983, 75544, 35822, 43664, 74352, 1321, 27567, 60487, 49137, 22518, 4572, 77721, 54090, 7911, 99725, 46455, 83763, 73049, 66191, 70483, 16867, 43707, 921, 82323, 90632, 66707, 80185, 86065, 10631, 28890, 36357, 45857, 33527, 9754, 46960, 86035, 4627, 56292, 30120, 74375, 37435, 42934, 66072, 50589, 70865, 34900, 76069, 36110, 86760, 79003, 30276, 2633, 28372, 57904, 41462, 85662, 97948, 43098, 76604, 98401, 92367, 91414, 18434, 85810, 15186, 86291, 86367, 6209, 17532, 13781, 26109, 19334, 15619, 68649, 70555, 39098, 47462, 74890, 33882, 83483, 47194, 37553, 95757, 35095, 48787, 28414, 89623, 18387, 16075, 23152, 12616, 37343, 24225, 60831, 97282, 33752, 21604, 97497, 79680, 51012, 59608, 48478, 35574, 71875, 33673, 90205, 83802, 58526, 52866, 22414, 62236, 62937, 38512, 71585, 64642, 87131, 9051, 17237, 2138, 54188, 56404, 45282, 58001, 43596, 44579, 57501, 30591, 88858, 4186, 40631, 71801, 67748, 25370, 32719, 32264, 58972, 50340, 6322, 38184, 26571, 98768, 50151, 2534, 27072, 80014, 74190, 3324, 83594, 22916, 70556, 22817, 52141, 10491, 30437, 52576, 9106, 96522, 70462, 7647, 12040, 47617, 53208, 14407, 25777, 33715, 64109, 34539, 24848, 64296, 18273, 13940, 86472, 64289, 97429, 14846, 70285, 42300, 42505, 98934, 57147, 38267, 26209, 66802, 91938, 69902, 39536, 52919, 70711, 43092, 98376, 69258, 9867, 41091, 37696, 98898, 12415, 10249, 36553, 81206, 15825, 60469, 87706, 51567, 98693, 17330, 75134, 11628, 5843, 43814, 87957, 89636, 29622, 67256, 12224, 76211, 56297, 91992, 34972, 6538, 32293, 9424, 19347, 62844, 18810, 77871, 18943, 99356, 91252, 60186, 79934, 4359, 32108, 70283, 4820, 36194, 60075, 41569, 73259, 69257, 41903, 43626, 79721, 53464, 5253, 12715, 59096, 69939, 82601, 39618, 35927, 10457, 20830, 28090, 89448, 53621, 8315, 15511, 29327, 12059, 49534, 7586, 95656, 14048, 92332, 27404, 31019, 75108, 91423, 81065, 47247, 97120, 4330, 66886, 83940, 35638, 15975, 46902, 84238, 16756, 64477, 38405, 65504, 76317, 89137, 11712, 31954, 3167, 78867, 89502, 6124, 83641, 57450, 45560, 84548, 98624, 19502, 32023, 60605, 35962, 81260, 99224, 40158, 89525, 52360, 78382, 96569, 77759, 34386, 85039, 88282, 39440, 44431, 99843, 77976, 72892, 54031, 5491, 95723, 38476, 26152, 16044, 62123, 12181, 1213, 48652, 41826, 60323, 60019, 78434, 78915, 74651, 44359, 2353, 33307, 23702, 49720, 55266, 93326, 7058, 48200, 83567, 83055, 43511, 18313, 17216, 48251, 63990, 82017, 6023, 32091, 42373, 43006, 78088, 88103, 43791, 11068, 89656, 9059, 84736, 94903, 43504, 99147, 73753, 49864, 90268, 27326, 23359, 38038, 79875, 9839, 37608, 92902, 42684, 37898, 97149, 55506, 74867, 72998, 36390, 98972, 64861, 76446, 35904, 29587, 53089, 47315, 21638, 72721, 71826, 66459, 79501, 38514, 51019, 19013, 13939, 32766, 28896, 46685, 28997, 90178, 22867, 87434, 36601, 82315, 24230, 69483, 47364, 55671, 53529, 83220, 85974, 43401, 20620, 2740, 47263, 50674, 79766, 86212, 477, 27070, 65756, 51028, 65701, 22010, 94220, 83180, 11569, 21615, 16414, 82130, 5032, 20435, 22070, 35354, 29763, 86419, 70980, 8503, 2149, 51184, 7796, 50132, 63962, 78856, 45703, 67131, 40389, 19608, 95280, 64079, 21116, 41433, 71733, 61635, 93615, 8720, 96396, 40159, 27478, 64453, 86591, 39591, 15702, 90457, 8189, 45920, 67474, 14921, 80688, 71700, 85767, 20217, 97313, 1616, 19487, 87582, 55275, 34779, 66206, 49730, 40277, 89032, 33081, 10332, 973, 47319, 51926, 51763, 96911, 38413, 78103, 97320, 55554, 63060, 41099, 13945, 96592, 98751, 46411, 78350, 27783, 5728, 33614, 84077, 13566, 23237, 47733, 94071, 97986, 20021, 52246, 48684, 94918, 55998, 86763, 94876, 33646, 62087, 42193, 74252, 42508, 58867, 3614, 70626, 36358, 61583, 20074, 65782, 78394, 50444, 20924, 51099, 83932, 40637, 34922, 89203, 7033, 90853, 4180, 18595, 151, 84914, 73120, 26918, 97903, 3765, 22669, 60295, 8756, 49816, 66714, 2888, 3015, 95791, 27920, 18065, 51069, 5830, 73821, 58846, 87019, 69438, 71611, 35453, 39522, 97552, 86559, 34837, 71455, 81534, 94095, 11285, 86451, 68742, 98548, 38993, 55197, 36177, 60541, 69473, 85080, 73386, 86424, 39301, 60948, 82681, 20468, 30856, 49321, 47915, 21789, 15992, 59878, 72563, 35336, 81237, 97077, 335, 30832, 58272, 18955, 74508, 59110, 87829, 32173, 68780, 36580, 92987, 33887, 4080, 54498, 47654, 18788, 5520, 66820, 66084, 64431, 64466, 96873, 88395, 25236, 26855, 9788, 26135, 30684, 38443, 90360, 80848, 40306, 2580, 24219, 66524, 38533, 36570, 65207, 89572, 51868, 20370, 25392, 64963, 92897, 99683, 48037, 62067, 95410, 43901, 10850, 88440, 96532, 83537, 86595, 89038, 34366, 92522, 45406, 32523, 97987, 59243, 38739, 67136, 40290, 69747, 93919, 84305, 52934, 81985, 12963, 27298, 12258, 4760, 73932, 61809, 25423, 43300, 9490, 37326, 19162, 68212, 34146, 14026, 39516, 98991, 99710, 34388, 54769, 91353, 62286, 77407, 15358, 63226, 13519, 20013, 92220, 72042, 53636, 48334, 5094, 28861, 25354, 56129, 9318, 89418, 14442, 1429, 81885, 70383, 64318, 11631, 60847, 73471, 49686, 51331, 44901, 43379, 96135, 9529, 98005, 63205, 3748, 33537, 94692, 3761, 66823, 16509, 99261, 36710, 53918, 599, 37413, 76723, 69842, 82742, 36613, 3542, 61629, 76697, 77874, 20319, 88524, 14862, 46840, 92065, 26168, 98285, 48547, 77975, 70847, 99404, 93571, 45919, 87731, 93354, 72874, 26163, 96644, 82271, 30364, 21735, 84063, 83920, 94184, 92731, 96251, 32115, 93926, 90548, 93706, 22450, 95054, 48499, 79604, 14950, 37322, 435, 38706, 5550, 25203, 33740, 22640, 24013, 96661, 90798, 14446, 75904, 77393, 85697, 12329, 76754, 11648, 19534, 25497, 82412, 98427, 44662, 73592, 69093, 15096, 57042, 97446, 95778, 84255, 24855, 93826, 70467, 16497, 70709, 67850, 38697, 26082, 75732, 94321, 2841, 78637, 4106, 33504, 75665, 4005, 79515, 26737, 76625, 44405, 23231, 77570, 53549, 61145, 81019, 23838, 63697, 86721, 7539, 65458, 18100, 25899, 90869, 43199, 79550, 24741, 9579, 98080, 60340, 5685, 44595, 91486, 5670, 69546, 14525, 18034, 75336, 39361, 13269, 90797, 50953, 54901, 79598, 35447, 89188, 21745, 11381, 26748, 21879, 20418, 39481, 85260, 51077, 13606, 39142, 44643, 21476, 29851, 30920, 97383, 40917, 55389, 43361, 18155, 13316, 87439, 5010, 53665, 35442, 5329, 41637, 14134, 88408, 3839, 65477, 493, 18764, 30751, 18230, 29821, 57071, 66592, 39218, 73221, 19174, 90393, 70230, 99452, 66290, 3083, 94883, 61528, 99315, 57466, 77708, 30475, 75945, 79381, 74582, 71854, 84954, 41601, 19657, 93417, 63587, 75775, 20621, 69289, 29494, 86646, 85547, 29579, 89870, 48611, 19041, 56437, 48234, 4052, 82464, 14325, 41904, 89554, 13152, 3712, 35265, 60447, 20600, 73414, 68871, 23622, 32338, 51425, 14377, 43392, 92171, 19453, 3922, 81545, 41400, 93969, 42171, 39629, 97757, 35310, 40382, 82404, 54755, 87930, 53045, 10594, 99156, 42530, 98346, 26160, 62508, 28266, 48290, 54781, 48156, 83126, 93000, 6247, 96678, 73123, 78203, 6098, 99398, 52376, 45297, 89402, 55951] }}

  - Repeat: {self.iterationsPerThread}
    Collection: *collection_param
    MetricsName: "q6"
    Operations:
    - OperationName: withTransaction
      OperationCommand:
        Options:
          WriteConcern:
            Level: majority
            Journal: true
          ReadConcern:
            Level: snapshot
          ReadPreference:
            ReadMode: primary
        OperationsInTransaction:
          -
            OperationName: findOne
            OperationMetricsName: reads
            OperationCommand:
              OnSession: true
              Filter:
                intField : {{$in : [33597, 38103, 82105, 44068, 54019, 18512, 56317, 70029, 66556, 1210, 12995, 94751, 87129, 4356, 748, 90067, 57115, 92133, 91743, 73316, 25957, 81524, 80536, 13282, 63985, 59518, 12603, 230, 23642, 26437, 19994, 28961, 54045, 35494, 57164, 46155, 65744, 57102, 54974, 25351, 82418, 72465, 73951, 84172, 17690, 53405, 3500, 67825, 66755, 62051, 25038, 96960, 54538, 2437, 84127, 12820, 59370, 12299, 84200, 34927, 13430, 26576, 34586, 99474, 74368, 56220, 84251, 31239, 37496, 7246, 70664, 36316, 29715, 53680, 8755, 34061, 14567, 93985, 23815, 14750, 34021, 9517, 92604, 57723, 93264, 77590, 75269, 56283, 64503, 52860, 91784, 29839, 38834, 34664, 45330, 30538, 28601, 95819, 77096, 97744, 1724, 95699, 44792, 24940, 92420, 75201, 54606, 10842, 82254, 56071, 30036, 99344, 66506, 23172, 21787, 41383, 7508, 65855, 67046, 31087, 93416, 19643, 95137, 74721, 22840, 32672, 73933, 16338, 60434, 61608, 86037, 12108, 45668, 60832, 71181, 43518, 9387, 48671, 68797, 37142, 4586, 41825, 41710, 85434, 63897, 71073, 23380, 23281, 32237, 47505, 77098, 98485, 32276, 60077, 80616, 49259, 42080, 59904, 75660, 65031, 94178, 88381, 29689, 68685, 65664, 15298, 79506, 62838, 33453, 20109, 37433, 47152, 62267, 80635, 7559, 32810, 87680, 881, 88135, 17433, 12785, 69062, 2737, 84974, 34789, 53122, 38853, 44868, 29666, 12561, 57463, 21462, 59020, 19707, 96888, 96443, 43668, 77628, 62713, 80597, 21226, 39568, 98109, 28231, 37034, 32176, 26689, 75213, 5351, 17964, 87704, 87901, 40956, 31188, 84422, 36536, 91217, 82089, 44543, 35692, 90064, 79253, 1912, 47898, 89270, 2243, 26263, 9846, 4476, 39825, 46871, 94109, 11626, 35150, 4443, 1070, 91271, 1271, 59684, 1887, 12761, 2018, 80453, 37945, 12672, 45014, 27689, 53268, 86336, 87120, 20070, 50852, 51059, 41319, 41407, 10714, 7190, 62980, 5992, 32750, 88039, 82676, 67745, 89750, 63908, 91208, 42523, 57573, 39335, 43308, 14059, 77758, 45962, 38946, 17768, 21862, 69488, 12372, 69871, 98497, 31061, 23459, 42221, 32296, 84166, 79517, 92922, 88422, 73989, 51011, 84656, 98124, 67091, 59862, 72296, 61822, 92086, 95438, 86880, 35296, 38526, 30429, 52911, 22776, 62536, 95635, 61993, 7588, 27720, 41967, 86242, 17474, 19821, 33697, 41301, 47356, 68427, 81752, 40597, 57041, 88546, 64529, 30639, 76051, 32489, 49035, 73714, 70218, 94791, 60786, 57997, 80840, 731, 98106, 65607, 93686, 20498, 13548, 3031, 89225, 86527, 89601, 94303, 28418, 97050, 81624, 50664, 47443, 51547, 71520, 34561, 82173, 22422, 26342, 15458, 8355, 33838, 35947, 69803, 13779, 61452, 51349, 30552, 67955, 36346, 6200, 80042, 87892, 69476, 59576, 61229, 70450, 30647, 3756, 9063, 23104, 87583, 65520, 76125, 96015, 94093, 92284, 5899, 26140, 83834, 48397, 65090, 10048, 16803, 47807, 83915, 10607, 67931, 10831, 88544, 9669, 11853, 13953, 96335, 51670, 81273, 30704, 23165, 56463, 20309, 81325, 57239, 62498, 85641, 71466, 16355, 8064, 24393, 49681, 90507, 13697, 91165, 69879, 47630, 18555, 42499, 55007, 69595, 94355, 95260, 718, 66120, 19355, 17484, 5641, 74952, 42130, 48049, 22409, 34052, 41101, 96792, 37047, 23408, 45020, 66844, 73798, 35426, 53564, 30662, 63313, 38845, 6000, 78109, 80775, 75462, 97658, 66765, 17180, 19231, 43539, 47340, 78223, 98300, 38755, 6243, 31366, 63621, 58811, 11554, 21625, 70080, 68561, 51793, 25345, 77489, 24451, 71510, 25128, 14269, 35896, 21424, 53821, 38183, 56543, 70484, 15726, 58178, 1472, 76113, 10509, 75029, 8222, 50345, 56837, 50903, 71050, 62246, 13445, 31046, 50072, 42060, 83613, 65725, 79739, 23532, 80541, 40605, 9808, 11432, 92178, 59977, 85438, 95441, 19969, 97056, 16860, 1114, 38021, 84497, 86425, 35106, 76777, 31022, 57724, 87020, 74001, 71151, 22471, 13272, 89612, 87416, 37284, 7755, 77215, 98287, 64134, 35400, 69339, 10965, 11356, 7102, 19515, 13363, 1316, 81578, 1599, 50104, 81160, 71503, 10687, 35981, 1192, 68711, 40895, 99848, 12123, 37166, 71564, 91398, 17379, 49295, 13078, 51440, 65113, 53590, 90709, 45181, 87478, 50047, 76602, 12510, 85224, 79726, 29135, 48800, 33188, 98196, 12465, 73839, 40183, 61643, 7144, 79304, 84723, 13864, 60777, 89460, 28904, 95057, 89827, 33406, 29580, 70270, 52801, 59210, 51834, 63794, 4453, 55626, 35890, 86842, 71045, 93496, 8993, 49510, 51253, 14215, 31679, 13221, 16397, 48857, 44314, 8150, 49515, 4519, 68193, 42821, 56408, 32109, 26785, 90083, 78947, 85103, 3073, 53698, 644, 76190, 70192, 13041, 77467, 11788, 25956, 7361, 44620, 43065, 94864, 74934, 90823, 61915, 31943, 74211, 88780, 48659, 76312, 7942, 37509, 40125, 89595, 10646, 4119, 47126, 98551, 2428, 77652, 32883, 21340, 20395, 19886, 10075, 80560, 2028, 37227, 60756, 31417, 51407, 73472, 31614, 64677, 63566, 70504, 92024, 54004, 28504, 90732, 77151, 83810, 49591, 66504, 49332, 44121, 13962, 51352, 76606, 94988, 74843, 84489, 47772, 53945, 93448, 81798, 7012, 46204, 61480, 91521, 26070, 77775, 29042, 54154, 20166, 20503, 93603, 621, 28362, 43523, 54899, 17581, 15286, 62826, 89174, 64327, 65367, 8287, 77803, 8300, 76499, 90647, 62861, 28739, 26940, 88302, 83816, 47277, 85079, 89250, 27480, 74548, 68238, 37316, 93169, 36879, 64153, 62678, 94693, 5538, 78046, 38994, 29961, 67514, 26226, 69442, 25099, 55844, 68357, 43502, 19121, 76009, 97590, 47784, 8643, 81987, 24506, 68814, 89172, 61579, 16335, 5562, 31202, 24938, 1860, 73727, 25524, 40974, 68713, 48354, 54303, 38617, 82975, 99711, 81602, 49513, 38217, 9077, 35975, 53043, 51119, 56988, 57855, 22107, 18948, 75162, 75643, 89347, 65341, 91534, 35125, 71222, 43566, 70802, 56656, 16179, 16478, 18952, 41218, 22904, 76267, 58543, 77801, 14915, 6194, 49842, 20532, 15818, 18774, 61870, 9589, 325, 31383, 23151, 11861, 26509, 73281, 23108, 14203, 64922, 52805, 7795, 52802, 21101, 47991, 70684, 27856, 94813, 1412, 44147, 90638, 71217, 43007, 93338, 91186, 71861, 58981, 97617, 59974, 86352, 71327, 97672, 34202, 99925, 6736, 61286, 56352, 88830, 90476, 91535, 40925, 74378, 96261, 359, 41661, 16996, 25911, 21773, 46200, 78367, 19069, 28193, 5897, 34793, 78744, 83711, 41119, 968, 49678, 59901, 13582, 61185, 45815, 97028, 79764, 63557, 83992, 61705, 80492, 39243, 7578, 43043, 21528, 15445, 50935, 10590, 68453, 43106, 99218, 23749, 25055, 61405, 27244, 64736, 99691, 44409, 20189, 9699, 63660, 77956, 26897, 33704, 86397, 62093, 91317, 77265, 43824, 13100, 76170, 65776, 82025, 93818, 37379, 14202, 39995, 65974, 20536, 60695, 80312, 82293, 76703, 70965, 32643, 17600, 54285, 35439, 67567, 97655, 26404, 55954, 33905, 65618, 65116, 30996, 79098, 90840, 41909, 31433, 29513, 20175, 97111, 65362, 76541, 10880, 7887, 96328, 89645, 8604, 11500, 26926, 92159, 61691, 70006, 84493, 79236, 75496, 44910, 91932, 82529, 77992, 24024, 75892, 69345, 84753, 40409, 31931, 46342, 49987, 73341, 13724, 39309, 15068, 73288, 54746, 47520, 7335, 96693, 16797, 47155, 80558, 73332, 74084, 47592, 3292, 82605, 98117, 83696, 84767, 96978, 17302, 554, 72056, 4365, 68925, 59726, 85866, 28230, 33806, 81662, 27723, 98880, 50803, 36858, 55912, 28066, 10722, 85169, 71679, 61894, 45221, 39239, 34499, 26844, 54074, 53641, 96613, 70077, 30884, 41880, 78220, 13286, 9226, 42173, 79900, 62837, 52569, 55600, 912, 61417, 3319, 10944, 27517, 94678, 86059, 82012, 43326, 53646, 58775, 96084, 95766, 62358, 3926, 91188, 61512, 37729, 62825, 78444, 72086, 62954, 4173, 61115, 41552, 10680, 32628, 54931, 26665, 34755, 39669, 81074, 26153, 22651, 43936, 33407, 21083, 45335, 22880, 58572, 66894, 50271, 77328, 64180, 31866, 76314, 99493, 95566, 91653, 85653, 93266, 25699, 46274, 3458, 26402, 24576, 15730, 25224, 85646, 80980, 69088, 45481, 81658, 59258, 82835, 38582, 3414, 91170, 25020, 40418, 92042, 12073, 59155, 40399, 51598, 84180, 37828, 92615, 58463, 5204, 84150, 47803, 26478, 84213, 68267, 25716, 19373, 81461, 97257, 59730, 44077, 3108, 68333, 51826, 15136, 11270, 96996, 13674, 89966, 23976, 84260, 36774, 53853, 61460, 56120, 36577, 78911, 60530, 67576, 78353, 95309, 1284, 14212, 55604, 77650, 93673, 89723, 84795, 57221, 60441, 5609, 1110, 62171, 73262, 94871, 40132, 41432, 95423, 13873, 60372, 33684, 58578, 14326, 36434, 88744, 6388, 1003, 92901, 56747, 81324, 71398, 93467, 48126, 97973, 65419, 62392, 16988, 57300, 35540, 17502, 29981, 48666, 85085, 29705, 8262, 35721, 31762, 26053, 4099, 49359, 82152, 14997, 58786, 89183, 56833, 99269, 81408, 52245, 56087, 72920, 67306, 25297, 22266, 39226, 57581, 20184, 72456, 32742, 99646, 44490, 62369, 67799, 59196, 80296, 71839, 21965, 41695, 51246, 74355, 37004, 16640, 21535, 67423, 39228, 90018, 8399, 31925, 70400, 43869, 21191, 85140, 83877, 25071, 42158, 84748, 52147, 61123, 86314, 10684, 36644, 28420, 37070, 73074, 61752, 16927, 47647, 69863, 16268, 82439, 92005, 28329, 95305, 25707, 25170, 17624, 95402, 36420, 74694, 87225, 76762, 77174, 91786, 76666, 16302, 21738, 27001, 92817, 29036, 60512, 97171, 45626, 75899, 91623, 53844, 50286, 27261, 84324, 56138, 21821, 70748, 79744, 70205, 47460, 66289, 3788, 23935, 47631, 11418, 3917, 65871, 35061, 10989, 95120, 54413, 57814, 73344, 8239, 1692, 46907, 3233, 92324, 6033, 79884, 44613, 36521, 87670, 60613, 70698, 3972, 29899, 68133, 36083, 62732, 9044, 49033, 99733, 6426, 55361, 57355, 38185, 2882, 88928, 57805, 89779, 35359, 62245, 59766, 20689, 54464, 15658, 20067, 55854, 5437, 83993, 57283, 80651, 13331, 3390, 97535, 7511, 93819, 72488, 28657, 4089, 63372, 2755, 71712, 36853, 43265, 81852, 76456, 11877, 10948, 74015, 40844, 10189, 71196, 35353, 34984, 84087, 69173, 28708, 89943, 40164, 59188, 43826, 17646, 29731, 4382, 78699, 22043, 10806, 26797, 72841, 81087, 68335, 95147, 93085, 90960, 96297, 23781, 93541, 66165, 27197, 64846, 88838, 56451, 58512, 73736, 4304, 39745, 22339, 74544, 28931, 90566, 31635, 53766, 25124, 4976, 31269, 10845, 71871, 24443, 94225, 49726, 21444, 63423, 76248, 33423, 56298, 64257, 33573, 88273, 45405, 52372, 41126, 91799, 75212, 84349, 24597, 85961, 55213, 53181, 33865, 39225, 1150, 24204, 42492, 23113, 23497, 80938, 54699, 46976, 19542, 22735, 24369, 5772, 29665, 17092, 41919, 18005, 47330, 92366, 31448, 45639, 34602, 15958, 54259, 71822, 21664, 95698, 49362, 71591, 33766, 16851, 35605, 7654, 20063, 91089, 42116, 97228, 78249, 10895, 64378, 17131, 7145, 93043, 24625, 46572, 60236, 43416, 51956, 21973, 83687, 83515, 40443, 32373, 19281, 47830, 60225, 26965, 82388, 82257, 48223, 86511, 39891, 15728, 44761, 90811, 46597, 79450, 63280, 51166, 42872, 32030, 33678, 65234, 92450, 47272, 38865, 5219, 58281, 64042, 62596, 61335, 87904, 30897, 56049, 72109, 38271, 93186, 93866, 56276, 55018, 61517, 40872, 85722, 84038, 56117, 52788, 67226, 96877, 71333, 42037, 31362, 27054, 4486, 61523, 35433, 33143, 47432, 85365, 5138, 8899, 94131, 38995, 66904, 4132, 97766, 79259, 92188, 31780, 87052, 46708, 88655, 63982, 90192, 72467, 89345, 34368, 9137, 47665, 93758, 51783, 69155, 96866, 55906, 66339, 4700, 90323, 10027, 71888, 38002, 25968, 25740, 93206, 50166, 6097, 27912, 2175, 18284, 66970, 65605, 95439, 14878, 2276, 21884, 20925, 44602, 44950, 24780, 4111, 90893, 52573, 56479, 27974, 96304, 51725, 30241, 67475, 35237, 62705, 9238, 38971, 69946, 23163, 61708, 32800, 2011, 68099, 22773, 75274, 7522, 40005, 71346, 11362, 66480, 61284, 38237, 16957, 6187, 20679, 82489, 42340, 83224, 57941, 83458, 50255, 76484, 42242, 56053, 89547, 4957, 27165, 73516, 92979, 80252, 87883, 7295, 3064, 48189, 87515, 5092, 92618, 58994, 73996, 10458, 85766, 63082, 51025, 59933, 89858, 17819, 37687, 70679, 35920, 91513, 56372, 79524, 35022, 17161, 86046, 33472, 5123, 17435, 75733, 3906, 73079, 94518, 57656, 90355, 69094, 27338, 61038, 44978, 93935, 79616, 77688, 77480, 93911, 3678, 56955, 66541, 37743, 30962, 10792, 85795, 40435, 92815, 91621, 80762, 48846, 71403, 5635, 65161, 16313, 10565, 32442, 15550, 93828, 87953, 83492, 7206, 54889, 39534, 34896, 86952, 32273, 63080, 55557, 84739, 29695, 26016, 81862, 46023, 67894, 30682, 65202, 92466, 16810, 59547, 90245, 41936, 84192, 87676, 39896, 76055, 37659, 76198, 35377, 36731, 28165, 12274, 72237, 95465, 58836, 13652, 74600, 49393, 98421, 32689, 48805, 32694, 20167, 23604, 57976, 7929, 55801, 15521, 10426, 31994, 19124, 89997, 22618, 42386, 4027, 41208, 10407, 59557, 68443, 98516, 53894, 53924, 20019, 94793, 62064, 26398, 62180, 80913, 28303, 58442, 98380, 1941, 50237, 90927, 95529, 82674, 22827, 11873, 21764, 93026, 64641, 27444, 37588, 42690, 73099, 48868, 22412, 15688, 64667, 46942, 81045, 7271, 93080, 55445, 49914, 4387, 63362, 83604, 99014, 82299, 98670, 88796, 32381, 11379, 12402, 55085, 54534, 61553, 61408, 77704, 24676, 16040, 7106, 32667, 57094, 21490, 80890, 57931, 90242, 77363, 15021, 92068, 31312, 5649, 25026, 87657, 8321, 445, 86283, 81444, 99565, 64200, 72536, 68802, 11846, 99908, 4607, 41700, 2218, 99288, 74632, 11988, 26903, 68290, 93076, 11794, 14506, 56877, 3303, 28425, 83395, 3196, 76953, 16715, 70653, 73818, 18560, 30608, 28660, 21303, 30491, 17636, 33243, 15786, 15092, 2818, 78251, 42958, 96018, 19959, 11279, 51892, 40554, 13579, 96158, 11947, 71309, 14930, 35415, 26766, 45359, 48793, 92713, 32762, 30287, 26587, 4779, 62672, 89349, 10459, 23877, 57900, 38661, 26303, 35093, 50276, 19940, 86140, 48210, 6231, 49539, 64183, 5981, 11099, 90079, 70689, 96916, 60320, 60850, 90361, 87975, 5606, 47099, 29697, 69715, 59274, 65841, 36338, 23730, 81209, 7239, 68018, 48045, 47717, 2328, 20943, 17972, 6874, 88632, 11217, 41271, 52354, 2152, 1234, 47626, 46252, 34464, 77442, 50194, 18083, 58663, 96256, 59213, 7146, 76775, 49140, 27316, 71561, 4142, 45122, 99178, 87987, 64401, 15474, 77766, 23070, 82431, 25157, 2229, 44145, 34978, 95282, 37090, 2825, 80131, 28257, 57482, 12238, 59689, 99211, 56758, 40419, 79387, 54915, 80888, 25581, 6559, 59350, 52499, 72039, 37406, 60476, 29059, 87662, 98227, 7641, 82504, 88850, 9261, 6781, 79017, 98875, 82759, 40212, 80880, 74323, 49345, 76487, 20086, 31246, 90716, 54575, 96082, 1872, 65818, 30336, 79532, 63164, 86670, 35346, 79324, 89249, 48366, 63957, 20586, 55658, 64775, 87427, 88492, 90094, 50043, 89459, 75712, 60940, 16556, 4187, 17929, 51298, 25163, 93564, 52112, 79605, 98414, 59566, 3092, 82374, 26533, 4775, 46087, 41990, 61554, 14148, 51970, 88953, 17298, 4499, 32490, 35107, 15278, 61832, 26703, 89721, 94271, 33241, 81804, 82639, 20398, 63212, 26486, 81632, 46363, 26945, 84593, 52301, 67396, 92045, 53056, 88115, 92866, 31728, 28365, 96377, 92389, 93301, 88326, 5535, 33090, 43555, 65608, 35238, 36639, 58799, 46337, 82843, 9902, 68373, 54426, 11406, 27582, 99417, 73051, 23073, 36340, 71343, 3312, 44136, 18040, 24261, 26255, 15145, 97989, 16953, 45550, 74392, 73928, 77666, 86211, 86963, 51607, 14683, 79622, 6301, 52156, 74793, 12854, 69292, 58331, 80710, 18349, 80904, 68309, 81128, 24746, 12511, 19981, 82852, 99953, 19440, 40611, 97983, 23309, 55962, 69685, 67000, 53781, 22104, 94194, 90860, 87848, 13551, 64425, 14223, 6883, 94932, 5664, 65743, 80493, 25527, 17516, 46408, 78296, 25142, 2335, 32813, 22323, 24018, 11409, 12428, 90032, 37264, 76251, 18333, 55457, 38436, 58024, 18290, 78858, 71179, 44157, 76523, 28100, 38438, 3655, 53390, 10385, 95634, 26096, 41076, 71183, 39074, 66489, 61076, 17428, 69010, 60251, 67210, 67186, 70390, 31817, 29820, 56714, 82546, 61334, 20649, 63135, 67827, 35663, 97509, 1100, 800, 51436, 40961, 88781, 38680, 94319, 55782, 81905, 75151, 34406, 4651, 30100, 60025, 23088, 67158, 67635, 1249, 8809, 36288, 9740, 63565, 8479, 61310, 96912, 5413, 39266, 88962, 15840, 95285, 33774, 51662, 50316, 11222, 18287, 46604, 67563, 92239, 78554, 30806, 59717, 33220, 19070, 64942, 29283, 47516, 59665, 23992, 80700, 95862, 21605, 60871, 17992, 5842, 66269, 34812, 14272, 69645, 99487, 96341, 73240, 44360, 57575, 19477, 21874, 60663, 77913, 84500, 82102, 46256, 60275, 11342, 35634, 46616, 94036, 46112, 77283, 17971, 45372, 5192, 10802, 19551, 8467, 38195, 85189, 27548, 88083, 812, 77454, 37737, 66175, 13448, 20883, 64537, 35576, 3868, 5952, 69936, 91824, 74860, 25453, 8216, 90251, 20112, 33085, 74031, 9162, 17056, 95284, 6234, 45255, 68183, 79862, 77316, 90191, 49898, 58755, 59367, 20981, 16476, 2717, 43966, 13825, 91620, 87824, 59241, 53611, 4823, 31469, 59287, 81783, 89015, 50324, 96228, 34486, 24913, 95972, 66441, 90336, 1875, 85742, 59263, 97398, 47534, 31029, 43234, 42881, 57611, 15097, 77421, 1625, 99578, 81223, 19526, 64046, 64394, 40373, 67101, 85286, 26832, 30407, 59097, 85092, 30122, 50719, 14943, 45889, 13596, 45189, 27485, 11309, 13166, 76848, 58713, 44534, 2477, 92765, 88337, 81041, 1088, 49155, 81604, 22008, 53290, 71436, 54828, 43406, 15827, 27602, 87934, 42894, 16148, 20825, 10805, 2242, 6573, 35059, 87859, 33764, 65457, 77869, 25241, 65667, 12947, 61137, 23648, 22355, 34890, 48131, 29200, 61733, 5721, 45019, 46415, 53508, 49174, 78860, 75170, 49821, 6364, 26087, 31330, 85385, 32984, 35585, 92370, 73787, 25420, 71673, 65942, 94642, 32553, 13397, 51296, 49950, 28565, 75351, 20866, 20376, 21532, 93521, 4683, 62703, 26470, 16229, 61644, 72193, 31420, 23839, 10780, 70326, 94215, 53361, 89377, 70606, 94469, 9288, 41149, 91496, 4378, 5358, 90142, 25261, 92632, 26506, 53913, 2502, 67853, 69880, 31077, 29758, 36865, 9860, 38479, 12757, 24156, 68617, 95535, 88248, 16423, 29881, 22247, 32352, 79305, 77041, 97190, 79234, 72957, 43607, 82704, 7666, 64304, 36478, 42836, 4149, 89228, 19095, 89679, 86566, 16506, 331, 75970, 21784, 63241, 52608, 21684, 63740, 83938, 26040, 98430, 43438, 13035, 55877, 15673, 63298, 8140, 93529, 25974, 91902, 35742, 66932, 37280, 67920, 76384, 5751, 19205, 60727, 36835, 46285, 24920, 96703, 98812, 8484, 55037, 82079, 45452, 39617, 29082, 80865, 64355, 57561, 29170, 58053, 68525, 98481, 6381, 22496, 6508, 46736, 15614, 72619, 4656, 98229, 8236, 35245, 57223, 25192, 11369, 45939, 91441, 24218, 43968, 4424, 87805, 28584, 73620, 81008, 37457, 71234, 80485, 9216, 33072, 64904, 86960, 74305, 99849, 48106, 77313, 96749, 30049, 29807, 72259, 97688, 19346, 91851, 87659, 16398, 45209, 81147, 4693, 47265, 94785, 32991, 31132, 58464, 40734, 36922, 57588, 84821, 92459, 81198, 57508, 915, 10164, 27035, 9293, 40937, 46048, 38823, 19292, 44707, 79738, 62331, 94449, 91606, 14942, 45601, 44640, 92965, 81690, 67498, 70448, 89481, 82565, 37649, 72201, 46109, 6290, 87835, 42066, 16036, 60820, 71717, 93962, 36846, 90777, 5922, 29882, 14923, 61279, 62310, 59745, 27529, 93684, 16807, 93226, 8924, 59509, 59428, 14037, 98047, 52657, 72759, 2193, 89082, 78149, 18647, 92732, 47024, 34576, 43102, 78696, 67360, 86883, 42641, 58403, 33389, 83460, 34546, 49493, 99422, 18675, 24351, 8799, 82359, 75635, 88420, 11121, 55853, 52732, 17619, 58398, 23572, 133, 72624, 5850, 76417, 59081, 39983, 53160, 1065, 12966, 33783, 66317, 5367, 99967, 58409, 6477, 79812, 6712, 50490, 62537, 3268, 69661, 38801, 4947, 57863, 45226, 98179, 74568, 95991, 2898, 3111, 39086, 56841, 24285, 62065, 85524, 25728, 90568, 56498, 89730, 71033, 68717, 82149, 57105, 40932, 77543, 15203, 50555, 58719, 10077, 79222, 91394, 96124, 59021, 91021, 12509, 54390, 53939, 26922, 51757, 98688, 43079, 52677, 17792, 74665, 49858, 44367, 66647, 11047, 6248, 92625, 72651, 2316, 19323, 82471, 87972, 15210, 75743, 84562, 80659, 35881, 5680, 61883, 89761, 11722, 82517, 51030, 64929, 35636, 78234, 99889, 16711, 85452, 32600, 59541, 80281, 45875, 1099, 57710, 59996, 61438, 49202, 2310, 65993, 67465, 77606, 40978, 74219, 25002, 98029, 48726, 17686, 56939, 37970, 38034, 10932, 57854, 48395, 16448, 51916, 72699, 42302, 7652, 19517, 61018, 37221, 48232, 42788, 26068, 67611, 47072, 3201, 95843, 82875, 11655, 94162, 4074, 18873, 44655, 49752, 32006, 1146, 5964, 83599, 74187, 98588, 71470, 60050, 1297, 90401, 92837, 84458, 32217, 52784, 28635, 57001, 34901, 58822, 37876, 60277, 54539, 71920, 50026, 85583, 62524, 37839, 88031, 97224, 65632, 19744, 54969, 91133, 32182, 6752, 62416, 81644, 78882, 60045, 17159, 74192, 70040, 90605, 85010, 39416, 61927, 37540, 1574, 25918, 83989, 72843, 34795, 50583, 83013, 43035, 76409, 17217, 17935, 89341, 65975, 47208, 39399, 74778, 25442, 94664, 20336, 45935, 31844, 59481, 27265, 6277, 55549, 54204, 6405, 18648, 45977, 23064, 91679, 21463, 62493, 37050, 28339, 71571, 89094, 93594, 7631, 95901, 17707, 35322, 55562, 57331, 44955, 67078, 73126, 22571, 82860, 37405, 90282, 89881, 81350, 12906, 40199, 87786, 61824, 29500, 18579, 49544, 34942, 44437, 4467, 98447, 30450, 44228, 55311, 11772, 25998, 81951, 21366, 69785, 80436, 45942, 95627, 17890, 84377, 5714, 73031, 36775, 64749, 62598, 61264, 37281, 67983, 75544, 35822, 43664, 74352, 1321, 27567, 60487, 49137, 22518, 4572, 77721, 54090, 7911, 99725, 46455, 83763, 73049, 66191, 70483, 16867, 43707, 921, 82323, 90632, 66707, 80185, 86065, 10631, 28890, 36357, 45857, 33527, 9754, 46960, 86035, 4627, 56292, 30120, 74375, 37435, 42934, 66072, 50589, 70865, 34900, 76069, 36110, 86760, 79003, 30276, 2633, 28372, 57904, 41462, 85662, 97948, 43098, 76604, 98401, 92367, 91414, 18434, 85810, 15186, 86291, 86367, 6209, 17532, 13781, 26109, 19334, 15619, 68649, 70555, 39098, 47462, 74890, 33882, 83483, 47194, 37553, 95757, 35095, 48787, 28414, 89623, 18387, 16075, 23152, 12616, 37343, 24225, 60831, 97282, 33752, 21604, 97497, 79680, 51012, 59608, 48478, 35574, 71875, 33673, 90205, 83802, 58526, 52866, 22414, 62236, 62937, 38512, 71585, 64642, 87131, 9051, 17237, 2138, 54188, 56404, 45282, 58001, 43596, 44579, 57501, 30591, 88858, 4186, 40631, 71801, 67748, 25370, 32719, 32264, 58972, 50340, 6322, 38184, 26571, 98768, 50151, 2534, 27072, 80014, 74190, 3324, 83594, 22916, 70556, 22817, 52141, 10491, 30437, 52576, 9106, 96522, 70462, 7647, 12040, 47617, 53208, 14407, 25777, 33715, 64109, 34539, 24848, 64296, 18273, 13940, 86472, 64289, 97429, 14846, 70285, 42300, 42505, 98934, 57147, 38267, 26209, 66802, 91938, 69902, 39536, 52919, 70711, 43092, 98376, 69258, 9867, 41091, 37696, 98898, 12415, 10249, 36553, 81206, 15825, 60469, 87706, 51567, 98693, 17330, 75134, 11628, 5843, 43814, 87957, 89636, 29622, 67256, 12224, 76211, 56297, 91992, 34972, 6538, 32293, 9424, 19347, 62844, 18810, 77871, 18943, 99356, 91252, 60186, 79934, 4359, 32108, 70283, 4820, 36194, 60075, 41569, 73259, 69257, 41903, 43626, 79721, 53464, 5253, 12715, 59096, 69939, 82601, 39618, 35927, 10457, 20830, 28090, 89448, 53621, 8315, 15511, 29327, 12059, 49534, 7586, 95656, 14048, 92332, 27404, 31019, 75108, 91423, 81065, 47247, 97120, 4330, 66886, 83940, 35638, 15975, 46902, 84238, 16756, 64477, 38405, 65504, 76317, 89137, 11712, 31954, 3167, 78867, 89502, 6124, 83641, 57450, 45560, 84548, 98624, 19502, 32023, 60605, 35962, 81260, 99224, 40158, 89525, 52360, 78382, 96569, 77759, 34386, 85039, 88282, 39440, 44431, 99843, 77976, 72892, 54031, 5491, 95723, 38476, 26152, 16044, 62123, 12181, 1213, 48652, 41826, 60323, 60019, 78434, 78915, 74651, 44359, 2353, 33307, 23702, 49720, 55266, 93326, 7058, 48200, 83567, 83055, 43511, 18313, 17216, 48251, 63990, 82017, 6023, 32091, 42373, 43006, 78088, 88103, 43791, 11068, 89656, 9059, 84736, 94903, 43504, 99147, 73753, 49864, 90268, 27326, 23359, 38038, 79875, 9839, 37608, 92902, 42684, 37898, 97149, 55506, 74867, 72998, 36390, 98972, 64861, 76446, 35904, 29587, 53089, 47315, 21638, 72721, 71826, 66459, 79501, 38514, 51019, 19013, 13939, 32766, 28896, 46685, 28997, 90178, 22867, 87434, 36601, 82315, 24230, 69483, 47364, 55671, 53529, 83220, 85974, 43401, 20620, 2740, 47263, 50674, 79766, 86212, 477, 27070, 65756, 51028, 65701, 22010, 94220, 83180, 11569, 21615, 16414, 82130, 5032, 20435, 22070, 35354, 29763, 86419, 70980, 8503, 2149, 51184, 7796, 50132, 63962, 78856, 45703, 67131, 40389, 19608, 95280, 64079, 21116, 41433, 71733, 61635, 93615, 8720, 96396, 40159, 27478, 64453, 86591, 39591, 15702, 90457, 8189, 45920, 67474, 14921, 80688, 71700, 85767, 20217, 97313, 1616, 19487, 87582, 55275, 34779, 66206, 49730, 40277, 89032, 33081, 10332, 973, 47319, 51926, 51763, 96911, 38413, 78103, 97320, 55554, 63060, 41099, 13945, 96592, 98751, 46411, 78350, 27783, 5728, 33614, 84077, 13566, 23237, 47733, 94071, 97986, 20021, 52246, 48684, 94918, 55998, 86763, 94876, 33646, 62087, 42193, 74252, 42508, 58867, 3614, 70626, 36358, 61583, 20074, 65782, 78394, 50444, 20924, 51099, 83932, 40637, 34922, 89203, 7033, 90853, 4180, 18595, 151, 84914, 73120, 26918, 97903, 3765, 22669, 60295, 8756, 49816, 66714, 2888, 3015, 95791, 27920, 18065, 51069, 5830, 73821, 58846, 87019, 69438, 71611, 35453, 39522, 97552, 86559, 34837, 71455, 81534, 94095, 11285, 86451, 68742, 98548, 38993, 55197, 36177, 60541, 69473, 85080, 73386, 86424, 39301, 60948, 82681, 20468, 30856, 49321, 47915, 21789, 15992, 59878, 72563, 35336, 81237, 97077, 335, 30832, 58272, 18955, 74508, 59110, 87829, 32173, 68780, 36580, 92987, 33887, 4080, 54498, 47654, 18788, 5520, 66820, 66084, 64431, 64466, 96873, 88395, 25236, 26855, 9788, 26135, 30684, 38443, 90360, 80848, 40306, 2580, 24219, 66524, 38533, 36570, 65207, 89572, 51868, 20370, 25392, 64963, 92897, 99683, 48037, 62067, 95410, 43901, 10850, 88440, 96532, 83537, 86595, 89038, 34366, 92522, 45406, 32523, 97987, 59243, 38739, 67136, 40290, 69747, 93919, 84305, 52934, 81985, 12963, 27298, 12258, 4760, 73932, 61809, 25423, 43300, 9490, 37326, 19162, 68212, 34146, 14026, 39516, 98991, 99710, 34388, 54769, 91353, 62286, 77407, 15358, 63226, 13519, 20013, 92220, 72042, 53636, 48334, 5094, 28861, 25354, 56129, 9318, 89418, 14442, 1429, 81885, 70383, 64318, 11631, 60847, 73471, 49686, 51331, 44901, 43379, 96135, 9529, 98005, 63205, 3748, 33537, 94692, 3761, 66823, 16509, 99261, 36710, 53918, 599, 37413, 76723, 69842, 82742, 36613, 3542, 61629, 76697, 77874, 20319, 88524, 14862, 46840, 92065, 26168, 98285, 48547, 77975, 70847, 99404, 93571, 45919, 87731, 93354, 72874, 26163, 96644, 82271, 30364, 21735, 84063, 83920, 94184, 92731, 96251, 32115, 93926, 90548, 93706, 22450, 95054, 48499, 79604, 14950, 37322, 435, 38706, 5550, 25203, 33740, 22640, 24013, 96661, 90798, 14446, 75904, 77393, 85697, 12329, 76754, 11648, 19534, 25497, 82412, 98427, 44662, 73592, 69093, 15096, 57042, 97446, 95778, 84255, 24855, 93826, 70467, 16497, 70709, 67850, 38697, 26082, 75732, 94321, 2841, 78637, 4106, 33504, 75665, 4005, 79515, 26737, 76625, 44405, 23231, 77570, 53549, 61145, 81019, 23838, 63697, 86721, 7539, 65458, 18100, 25899, 90869, 43199, 79550, 24741, 9579, 98080, 60340, 5685, 44595, 91486, 5670, 69546, 14525, 18034, 75336, 39361, 13269, 90797, 50953, 54901, 79598, 35447, 89188, 21745, 11381, 26748, 21879, 20418, 39481, 85260, 51077, 13606, 39142, 44643, 21476, 29851, 30920, 97383, 40917, 55389, 43361, 18155, 13316, 87439, 5010, 53665, 35442, 5329, 41637, 14134, 88408, 3839, 65477, 493, 18764, 30751, 18230, 29821, 57071, 66592, 39218, 73221, 19174, 90393, 70230, 99452, 66290, 3083, 94883, 61528, 99315, 57466, 77708, 30475, 75945, 79381, 74582, 71854, 84954, 41601, 19657, 93417, 63587, 75775, 20621, 69289, 29494, 86646, 85547, 29579, 89870, 48611, 19041, 56437, 48234, 4052, 82464, 14325, 41904, 89554, 13152, 3712, 35265, 60447, 20600, 73414, 68871, 23622, 32338, 51425, 14377, 43392, 92171, 19453, 3922, 81545, 41400, 93969, 42171, 39629, 97757, 35310, 40382, 82404, 54755, 87930, 53045, 10594, 99156, 42530, 98346, 26160, 62508, 28266, 48290, 54781, 48156, 83126, 93000, 6247, 96678, 73123, 78203, 6098, 99398, 52376, 45297, 89402, 55951] }}

- Name: IndexSetup
  Type: RunCommand
  Threads: {self.threadCount}
  Database: genny_qebench2
  ClientName: EncryptedPool
  Phases:
  - *Nop
  - *create_index_phase
  {nop_phases}

- Name: LoggingActor0
  Type: LoggingActor
  Threads: 1
  Phases:
  {logging_phases}

{self._generateAutoRun()}

""")

    return str_buf.getvalue()


def main():
  # type: () -> None
  """Execute Main Entry point."""
  parser = argparse.ArgumentParser(description='MongoDB QE Workload Generator.')

  parser.add_argument('-v', '--verbose', action='count', help="Enable verbose tracing")

  parser.add_argument('--no_load', action='store_true', default=False,
                      help='Do not do the load phase')

  parser.add_argument('--no_query', action='store_true', default=False,
                      help='Do not do the query phase')

  args = parser.parse_args()

  if args.verbose:
      logging.basicConfig(level=logging.DEBUG)


  print("QueryOnly Experiments")
  for ex in EXPERIMENTS:
      for cf in ex["contentionFactors"]:
        for tc in ex["threadCounts"]:
          testName = f"Query-{ex['name']}-{cf}-{tc}"


          writer = WorkloadWriter(testName, ex["coll"], ex["queries"], ex["encryptedFieldCount"], cf, tc, not args.no_load, not args.no_query)
          buf = writer.serialize()

          print(f"Writing src/workloads/encrypted3/{testName}.yml")

          with open(f"src/workloads/encrypted3/{testName}.yml", 'w+') as testFile:
            testFile.write(buf)

          # sys.exit(1)

if __name__== "__main__":
    main()
