# gen_ds.py

import pandas as pd
import json
from dataStructures import *
import os


def main():
    config = Config() # set the thresholds
    dataDir = "collection"

    if not os.path.exists(dataDir):
        os.makedirs(dataDir)

    path = dataDir

    # ls contains all the kinds of datasets we want to generate
    ls  = ["vlf", "mlf", "lf", "hf", "mhf", "vhf", "blimit", "pbl"]

    # Generate maps
    for typeDS in ls:
        nDocs = 100000
        if typeDS == "blimit":
            nDocs = 1000000
        with open(f"maps_{typeDS}.yml", "w") as fh:
            print("Generating: %s" % (typeDS))

            fh.write("""SchemaVersion: 2018-07-01
Owner: "@10gen/server-security"
Description: |
    Mimics a YCSB workload, with queryable encryption enabled. Performs queries on an encrypted
    field, instead of _id, during the read/update phase.\n\n""")

            fh.write("##############################\n")

            fh.write("########## %s\n" % (typeDS))

            path = dataDir + "/" + typeDS
            if not os.path.exists(path):
                os.makedirs(path)

            # create the dataset
            # NOTE: nfields defaults to 10. But can change them too
            ds = Dataset(config, nDocs, typeDS)
            # NOTE: comment sanityCheckData if datagen is taking too long
            # sanityCheckData(ds)

            for k in ds.fieldDescDict.keys():
                vf = ds.fieldDescDict[k].valFreqsDict
                path = "map_%s_%s" % (typeDS, k)

                fh.write("%s: &%s\n" % (path, path))
                fh.write("    id: %s\n" % (path))
                fh.write("    from:\n" )
                for v in vf.keys():
                    fh.write("        %s: %s\n" % (v, vf[v]))
                fh.write("\n")

            fh.write("\n")

            # # Generate documents to insert
            # for field_count in [0, 1, 5, 10]:
            #     key = "document_insert_%s_f%d" % (typeDS, field_count)

            #     fh.write("%s:\n" % (key))

            #     for i in range(10):
            #         map_key = "map_%s_f%d" % (typeDS, i)
            #         fh.write("    field%d:  {^TakeRandomStringFromFrequencyMapSingleton: *%s }\n" % (i, map_key))
            #     fh.write("\n")
            # Generate documents to insert
            key = "document_insert_%s" % (typeDS)

            fh.write("%s:\n" % (key))
            fh.write("    _id:     {^Inc: {start: 1, multiplier: {^Parameter: {Name: \"multiplier\", Default: 0}}}}\n")

            for i in range(1, 11):
                map_key = "map_%s_f%d" % (typeDS, i)
                fh.write("    field%d:  {^TakeRandomStringFromFrequencyMapSingleton: *%s }\n" % (i, map_key))
            fh.write("\n")

        #sys.exit(1)




if __name__== "__main__":
    main()
