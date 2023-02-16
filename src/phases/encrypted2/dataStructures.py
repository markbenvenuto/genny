import random
import sys
import numpy as np

# NOTE: All thresholds and frequencies in this file are in absolute terms

class Range:
    def __init__(self, lb, ub) -> None:
        self.lb = lb
        self.ub = ub

    def __contains__(self, num):
        return (self.lb <= num <= self.ub)

# lfth < mlfth < lfth < hfth < mhfth
class Config:
    def __init__(self, vlfth = 10, mlfth = 100, lfth = 1000, hfth = 10000, mhfth = 50000):
        # all thresholds are upperbounds to the ranges. 
        # For example, if very low freqs are from [1, 10], then vlfth = 10
        self.markersList = ["vlf", "mlf", "lf", "hf", "mhf", "vhf"]
        self.ranges = {}
        self.ranges["vlf"] = Range(1, vlfth) 
        self.ranges["mlf"] = Range(vlfth + 1, mlfth)
        self.ranges["lf"] = Range(mlfth + 1, lfth)
        self.ranges["hf"] = Range(lfth + 1, hfth)
        self.ranges["mhf"] = Range(hfth + 1, mhfth)
        self.ranges["vhf"] = Range(mhfth + 1, sys.maxsize)


    def toJSONDict(self):
        s = {}
        for name, r in self.ranges.items():
            s[name] = [r.lb, r.ub]
        return s

    # takes a number as input and outputs a string describing where does that freq fall
    def descFreq(self, num):
        for name, r in self.ranges.items():
            if num in r:
                return name
        raise Exception("Out of bounds num")

class Dataset:
    def __init__(self, config, ndocs, typeDS, nfields = 10):
        
        # metadata
        self.ndocs = ndocs # number of documents in the dataset
        self.nfields = nfields # nfields
        self.fieldDescDict = {} # fieldName : ValueFreqs Object
        self.typeDS = typeDS 
        self.config = config
        # actual data
        self.documentsList = [] # array of n_docs Document objects
        
        # generate Fields and values for all the fields following the right distribution
        for i in range(nfields):
            fname = 'f'+str(i+1)
            
            if (typeDS in config.markersList):
                # what is the range of frequencies of values for this field
                freqRange = config.ranges[typeDS]
                # generate all the values in this range
                freqList = self.generateValueFreqs(ndocs, freqRange.lb, freqRange.ub)
            elif (typeDS == 'pbl'):
                freqList = self.generatePBLValueFreqs(ndocs)
            else:
                raise Exception("Wrong typeDS")
            assert(sum(freqList) == ndocs)

            self.fieldDescDict[fname] = ValueFreqs(fname, freqList, config)
        # generate data following the right distribution
        self.generateData()

    # NOTE: this function is written very specifically to work only with ndocs = 100k. 
    # TODO: make this general to work any values of ndocs
    def generatePBLValueFreqs(self, ndocs):

        freqList = []
        sumFreq = 0

        # generate at least one value in each bucket
        for marker in self.config.markersList:
            mrange = self.config.ranges[marker]
            freqlb = mrange.lb
            frequb = mrange.ub

            if (marker == "mhf"):
                f = random.randint(10001, 30000)
            elif (marker == "vhf"):
                f = random.randint(50001, 55000)
            else:
                f = random.randint(freqlb, frequb)
        
            sumFreq += f
            assert(sumFreq <= 100000)
            freqList.append(f)
        
        # assign the remaining values to rest of the buckets following a zipf distribution
        a = 2
        x = np.random.zipf(a, size = 100000-sumFreq)
        unique, counts = np.unique(x, return_counts=True)
        for c in counts:
            sumFreq += int(c)
            freqList.append(int(c))
        
        assert(sumFreq == 100000)
        return freqList

    def generateValueFreqs(self, ndocs, freqlb, frequb):
        freqList = []
        nvalues = 0
        sumFreq = 0

        # TODO: the last value might not be in the range of freqlb and frequb
        while(sumFreq < ndocs):
            f = random.randint(freqlb, frequb)
            
            if (sumFreq + f > ndocs):
                f = ndocs - sumFreq

            freqList.append(f)
            sumFreq += f
            nvalues += 1

        return freqList # can return nvalues if needed


    def toJSONDict(self):
        s = {}
        s["typeDS"] = self.typeDS
        s["rangeDesc"] = self.config.toJSONDict()
        s["fieldsDesc"] = {}
        for fName, valFreqsObj in self.fieldDescDict.items():
            s["fieldsDesc"][fName] = valFreqsObj.toJSONDict()
        return s


    def generateData(self):
        nDocs = self.ndocs
        # nFields = self.nfields
        fieldNames = self.fieldDescDict.keys()
        fieldDescDict = self.fieldDescDict

        # generate documents with only their fields set. Values for those fields are still to be set
        for i in range(nDocs):
            self.documentsList.append(Document(fieldNames))
        

        for fieldName, valDescObj in fieldDescDict.items():
            valFreqsDict = valDescObj.valFreqsDict
            # a random permutation of {0, ..., nDocs - 1}
            randPerm = np.random.permutation(nDocs) 
            i = 0
            for valname, freq in valFreqsDict.items():
                for j in range(freq):
                    self.documentsList[randPerm[i]].dataDict[fieldName] = valname
                    i += 1


    
class ValueFreqs:
    def __init__(self, fname, freqList, config):
        self.fname = fname
        self.valFreqsDict = {} # {valName: freq of this value}
        self.valuesList = [] # array of all value names
        self.nvalues = 0
        self.config = config
        
        self.ranges = {}
        for n in config.markersList:
            self.ranges[n+str("ValList")] = []
 
        for i in range(len(freqList)):
            valname = "v"+str(i+1)
            # valname = i+1
            self.valuesList.append(valname)
            self.valFreqsDict[valname] = freqList[i]
            
            for n, r in config.ranges.items():
                if freqList[i] in r:
                    self.ranges[n+str("ValList")].append(valname)
                    continue
        
        self.nvalues = len(freqList)
    
    def __repr__(self): 
        return f"<\n \
                Fieldname: {self.fname} \n\
                nValues: {self.nvalues} \n\
                valFreqs: {self.valFreqsDict} \n\
                ranges: {self.ranges}\
            >\n" 
        
    def toJSONDict(self):
        s = {}
        s["valFreqs"] = self.valFreqsDict
        for n, l in self.ranges.items():
            s[n] = l
        return s

class Document:
    def __init__(self, fieldNames = []):
        self.nfields = len(fieldNames)
        self.dataDict = {} # will have (f: v) pairs

        for field in fieldNames:
            self.dataDict[field] = ""

    def __repr__(self) -> str:
        return f"{self.dataDict}"

    def toJSONDict(self):
        return self.dataDict
