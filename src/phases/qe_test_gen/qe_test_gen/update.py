
import math

import frequency_map

"""
Experiment Set u.1: Update unencrypted fields on unencrypted collection
coll = pbl
enc = 0
((ffield, fval), (ufield, uval)) in 
((_id, fixed), (fixed_10, fixed)), 
((fixed_10, fixed_vlf), (fixed_10, uar), 
((uar_[1, 10], uar_alllow), (uar_[1, 10], uar))
cf in {1, 4, 8, 16}
tc in {4, 8, 16}

Experiment Set u.2: Update unecrypted fields on partially encrypted collection
coll = pbl
enc = 5
((ffield, fval), (ufield, uval)) in 
((_id, fixed), (fixed_10, fixed)), 
((fixed_10, fixed_vlf), (fixed_10, uar), 
((uar_[6, 10], uar_alllow), (uar_[6, 10], uar))
cf in {1, 4, 8, 16}
tc in {4, 8, 16}

Experiment Set u.3: Update encrypted fields on partially encrypted collection
coll = pbl
enc = 5
((ffield, fval), (ufield, uval)) in 
((_id, fixed), (fixed_1, fixed)), 
((fixed_1, fixed_vlf), (fixed_1, uar), 
((uar_[1, 5], uar_alllow), (uar_[1, 5], uar))
cf in {1, 4, 8, 16}
tc in {4, 8, 16}

Experiment Set u.4: Update encrypted fields on fully encrypted collection
coll = pbl
enc = 10
((ffield, fval), (ufield, uval)) in 
((_id, fixed), (fixed_1, fixed)), 
((fixed_1, fixed_vlf), (fixed_1, uar), 
((uar_[1, 10], uar_alllow), (uar_[1, 10], uar))
cf in {1, 4, 8, 16}
tc in {4, 8, 16}
"""
from jinja2 import Environment, PackageLoader, select_autoescape
env = Environment(
    loader=PackageLoader("qe_test_gen"),
    variable_start_string="<<",
    variable_end_string=">>",
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=select_autoescape()
)

EXPERIMENTS = [
  {
    # Experiment Set u.1: Update unencrypted fields on unencrypted collection
    "name" : "es1",
    "coll" : "pbl",
    "encryptedFieldCount" : 4,
    "threadCounts" : [4, 8, 16],
    "contentionFactors" : [1,4,8,16],
    "updates" : [
      {
        "query" : {
          "field" : "_id",
          "value" : "fixed"
        },
        "update" : {
          "field" : "fixed_10",
          "value" : "fixed"
        }
      },
      {
        "query": {
          "field": "fixed_10",
          "value": "fixed_vlf"
        },
        "update": {
          "field": "fixed_10",
          "value": "uar",
        },
      },
      {
        "query": {
          "field": "uar_[1,10]",
          "value": "uar_alllow"
        },
        "update": {
          "field": "uar_[1,10]",
          "value": "uar"
        },
      },
    ]
  }
]
DOCUMENT_COUNT=100000

class LoadPhase:
  def __init__(self, env):
    self.env = env

  def context(self):
    return {}

  def generate(self):
    template = self.env.get_template("load_phase.jinja2")
    return template

class UpdatePhase:
  def __init__(self, env, queryField, queryValue, updateField, updateValue):
    self.env = env
    self.queryField = queryField
    self.queryValue = queryValue
    self.updateField = updateField
    self.updateValue = updateValue

  def context(self):
    return {
      'query_field': self.queryField,
      'query_value': self.queryValue,
      'update_field': self.updateField,
      'update_value': self.updateValue
    }

  def generate(self):
    template = self.env.get_template("update_phase.jinja2")
    return template

class ExperimentParser:
  def __init__(self, ex):
    self.ex = ex

  def transformField(selector):
    """Convert a field selector in a query against a field or a set of fields"""
    if selector is "_id":
      return "_id"

    # Fixed field
    if selector.startswith("fixed_"):
      return "field" + selector.replace("fixed_", "")
  
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
    elif selector == "fixed":
      return "49999"
    elif selector.startswith("fixed_"):
      return fb.fixed_bucket(selector.replace("fixed_", ""))
    elif selector.startswith("uar_alllow"):
      return fb.uar_all_low()
    
    raise NotImplemented()

  def parseFieldValue(self, target):
    return (ExperimentParser.transformField(target['field']),  ExperimentParser.transformValueSelector(None, target['value']))

  def makePhases(self, env):
    query = self.parseFieldValue(self.ex['query'])
    update = self.parseFieldValue(self.ex['update'])
    return [LoadPhase(env), UpdatePhase(env, query[0], query[1], update[0], update[1])]

class Workload:
  def __init__(self, ex, cf, tc):
    self.name = ex['name']
    self.contentionFactor = cf
    self.encryptedFields = ex['encryptedFieldCount']
    self.threadCount = tc
    self.collectionName = ex['coll']

    self.parser = ExperimentParser(ex['updates'][0])

  def asContext(self):
    phases = self.parser.makePhases(env)

    context =  {
      "testName": f"UpdateOnly-{self.name}-{cf}-{tc}",
      "contentionFactor": self.contentionFactor,
      "encryptedFields": self.encryptedFields,
      "threadCount": self.threadCount,
      "collectionName": self.collectionName,
      "iterationsPerThread": math.floor(DOCUMENT_COUNT / self.threadCount),
      "maxPhase": len(phases),
      "shouldAutoRun": True,
      "phases": phases
    }

    return context
    

template = env.get_template("update_only.jinja2")
for ex in EXPERIMENTS:
    for cf in ex["contentionFactors"]:
        for tc in ex["threadCounts"]:
            workload = Workload(ex, cf, tc)
            print(template.render(workload.asContext()))
