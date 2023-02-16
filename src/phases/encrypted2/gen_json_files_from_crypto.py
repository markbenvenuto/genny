import pandas as pd
import json
from dataStructures import *
import os

# checks if the data has the right frequencies
def sanityCheckData(ds):
    docList = ds.documentsList

    # convert data to a format understandable to pandas
    convertData = {}
    for i in range(10):
        convertData['f'+str(i+1)] = []
    
    for doc in docList:
        for f, v in doc.dataDict.items():
            convertData[f].append(v)

    # load data in pandas
    df = pd.DataFrame.from_dict(convertData, orient='columns')

    # check if each field in the dataset has the right frequency
    freqDescDict = ds.fieldDescDict
    for fieldName, valFreqsObj in freqDescDict.items():
        valCounts = df[fieldName].value_counts()
        # print("********", valCounts)
        valFreqsDict = valFreqsObj.valFreqsDict
        for valname, freq in valFreqsDict.items():
            # print(f'valname: {valname} \t expFreq: {freq} \t freq: {valCounts[valname]}')
            assert(valCounts[valname] == freq)


def writeCollection(ds, path):
    nDocs = ds.ndocs
    
    for i in range(nDocs):
        filename = "file" + str(i) + ".json"
        document = ds.documentsList[i]
        s = document.toJSONDict()
        configFile = open(path + "/" + filename, 'w')
        configFile.write(json.dumps(s, indent = 4))
        configFile.close()



def main():
    nDocs = 100000
    config = Config() # set the thresholds
    dataDir = "collection"

    if not os.path.exists(dataDir):
        os.makedirs(dataDir)

    path = dataDir

    # ls contains all the kinds of datasets we want to generate
    ls  = ["vlf", "mlf", "lf", "hf", "mhf", "vhf", "pbl"]
 
    for typeDS in ls:
        print("*************", typeDS)

        path = dataDir + "/" + typeDS
        if not os.path.exists(path):
            os.makedirs(path)

        # create the dataset
        # NOTE: nfields defaults to 10. But can change them too
        ds = Dataset(config, nDocs, typeDS)
        # NOTE: comment sanityCheckData if datagen is taking too long
        # sanityCheckData(ds)

        # write freq description of each field to a config file 
        s = ds.toJSONDict()
        configFile = open(path + "/configFile.json", 'w')
        configFile.write(json.dumps(s, indent = 4))
        configFile.close()

        # # write all the data files inside of data folder
        # path += "/data"
        # if not os.path.exists(path):
        #     os.makedirs(path)
        # writeCollection(ds, path)
        sys.exit(1)




if __name__== "__main__":
    main()
