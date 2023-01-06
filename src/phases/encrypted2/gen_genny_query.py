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
DOCUMENT_COUNT = 100000
QUERY_COUNT = 10000

# Test Values
# DOCUMENT_COUNT = 100
# QUERY_COUNT = 10

EXPERIMENTS = [
  # {
  #   # Experiment Set q.1: Query unencrypted fields on unencrypted collection
  #   "name" : "es1",
  #   "coll" : "pbl",
  #   "encryptedFieldCount" : 0,
  #   "threadCounts" : [1,4,8,16],
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
    "contentionFactors" : [1,4], #,8,16],
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
  {
    # Experiment Set q.3: Query encrypted fields on partially encrypted collection
    "name" : "es3",
    "coll" : "pbl",
    "encryptedFieldCount" : 5,
    "threadCounts" : [1,4,8,16],
    "contentionFactors" : [1,4], #,8,16],
    "queries" : [
      {
        "field" : "fixed_1",
        "value" : "fixed_hf"
      },
      {
        "field" : "fixed_1",
        "value" : "uar"
      },
      {
        "field" : "uar_[1,5]",
        "value" : "uar"
      },
      {
        "field" : "uar_[1,5]",
        "value" : "uar_alllow"
      },
    ]
  },
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

    count = 0
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

LoadPhase: &load_phase
  Repeat: {self.iterationsPerThread}
  Collection: &collection_param {{^Parameter: {{Name: "Collection", Default: "{self.collectionName}"}}}}
  MetricsName: "load"
  Operations:
  - OperationName: insertOne
    OperationMetricsName: inserts
    OperationCommand:
      Document:
        LoadConfig:
          Path: ../../phases/encrypted2/maps_{self.map_name}.yml
          Key: {self.documentKey}
          Parameters:
            Database: ignored


Actors:
- Name: InsertActor
  Type: CrudActor
  Threads: {self.threadCount}
  Database: genny_qebench2
  ClientName: EncryptedPool
  Phases:
  {load_phase}
  {query_phases}


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
